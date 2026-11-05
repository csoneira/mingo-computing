#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_SIMULATION/MINGO_DICTIONARY_CREATION_AND_TEST/STEPS/STEP_1_SETUP/STEP_1_3_BUILD_DICTIONARY/build_dictionary.py
Purpose: STEP 1.3 — Build dictionary and holdout dataset from transformed feature space.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-11
Runtime: python3
Usage: python3 PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_SIMULATION/MINGO_DICTIONARY_CREATION_AND_TEST/STEPS/STEP_1_SETUP/STEP_1_3_BUILD_DICTIONARY/build_dictionary.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import re
import sys
import warnings
from typing import Sequence

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
STEP_ROOT = PIPELINE_DIR if (PIPELINE_DIR / "STEP_1_SETUP").exists() else PIPELINE_DIR / "STEPS"
DEFAULT_CONFIG = (
    STEP_ROOT / "STEP_1_SETUP" / "STEP_1_1_COLLECT_DATA" / "INPUTS" / "config_step_1.1_method.json"
)
MODULES_DIR = PIPELINE_DIR / "STEPS" / "MODULES" if (PIPELINE_DIR / "STEPS" / "MODULES").exists() else PIPELINE_DIR / "MODULES"
DEFAULT_INPUT = (
    STEP_DIR.parent / "STEP_1_2_TRANSFORM_FEATURE_SPACE" / "OUTPUTS" / "FILES" / "transformed_feature_space.csv"
)
DEFAULT_STEP12_MANIFEST = (
    STEP_DIR.parent / "STEP_1_2_TRANSFORM_FEATURE_SPACE" / "OUTPUTS" / "FILES" / "feature_space_manifest.json"
)
DEFAULT_STEP11_COLLECTED = (
    STEP_DIR.parent / "STEP_1_1_COLLECT_DATA" / "OUTPUTS" / "FILES" / "collected_data.csv"
)

FILES_DIR = STEP_DIR / "OUTPUTS" / "FILES"
PLOTS_DIR = STEP_DIR / "OUTPUTS" / "PLOTS"
FILES_DIR.mkdir(parents=True, exist_ok=True)
PLOTS_DIR.mkdir(parents=True, exist_ok=True)

_FIGURE_COUNTER = 0
FIGURE_STEP_PREFIX = "1_3"


def _save_figure(fig: plt.Figure, path: Path, **kwargs) -> None:
    global _FIGURE_COUNTER
    _FIGURE_COUNTER += 1
    out_path = Path(path)
    out_path = out_path.with_name(f"{FIGURE_STEP_PREFIX}_{_FIGURE_COUNTER}_{out_path.name}")
    fig.savefig(out_path, **kwargs)


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


logging.basicConfig(
    format="[%(levelname)s] STEP_1.3 — %(message)s", level=logging.INFO
)
log = logging.getLogger("STEP_1.3")

if str(MODULES_DIR) not in sys.path:
    sys.path.insert(0, str(MODULES_DIR))
try:
    from feature_space_config import (  # noqa: E402
        extract_feature_dimensions,
        load_feature_space_config,
        resolve_feature_space_config_path,
        resolve_selected_feature_space_columns,
    )
except Exception as exc:  # pragma: no cover - import failure is fatal
    raise RuntimeError(f"Could not import feature_space_config from {MODULES_DIR}: {exc}") from exc
try:
    from step1_manifest import (  # noqa: E402
        load_step1_feature_manifest,
        manifest_primary_feature_columns,
    )
except Exception as exc:  # pragma: no cover - import failure is fatal
    raise RuntimeError(f"Could not import step1_manifest from {MODULES_DIR}: {exc}") from exc

TT_RATE_COLUMN_RE = re.compile(r"^(?P<prefix>.+?)_tt_(?P<label>[^_]+)_rate_hz$")
PHYSICAL_TT_RATE_LABELS = (
    "1234",
    "123",
    "124",
    "134",
    "234",
    "12",
    "13",
    "14",
    "23",
    "24",
    "34",
)
TT_PREFIX_PRIORITY = [
    "post",
    "fit",
    "list",
    "cal",
    "clean",
    "raw",
    "corr",
    "definitive",
]


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


def _resolve_events_column(df: pd.DataFrame) -> str | None:
    candidates = (
        "n_events",
        "selected_rows",
        "requested_rows",
        "generated_events_count",
        "num_events",
        "event_count",
    )
    for col in candidates:
        if col in df.columns:
            return col
    return None


def _normalize_tt_label(label: object) -> str:
    text = str(label).strip()
    if not text:
        return ""
    try:
        value = float(text)
    except (TypeError, ValueError):
        return text
    if not np.isfinite(value):
        return ""
    if float(value).is_integer():
        return str(int(value))
    return text


def _is_multi_plane_tt_label(label: object) -> bool:
    norm = _normalize_tt_label(label)
    if len(norm) < 2:
        return False
    if not all(ch in {"1", "2", "3", "4"} for ch in norm):
        return False
    return len(set(norm)) == len(norm)


def _tt_prefix_rank(prefix: str) -> int:
    try:
        return TT_PREFIX_PRIORITY.index(prefix)
    except ValueError:
        return len(TT_PREFIX_PRIORITY)


def _resolve_physical_tt_rate_columns_from_names(columns: list[str]) -> tuple[str | None, dict[str, str]]:
    wanted = set(PHYSICAL_TT_RATE_LABELS)
    by_prefix: dict[str, dict[str, str]] = {}
    for col in columns:
        text = str(col).strip()
        match = TT_RATE_COLUMN_RE.match(text)
        if match is None:
            continue
        prefix = str(match.group("prefix")).strip()
        if "_to_" in prefix:
            continue
        label = _normalize_tt_label(match.group("label"))
        if not _is_multi_plane_tt_label(label) or label not in wanted:
            continue
        by_prefix.setdefault(prefix, {})[label] = text

    if not by_prefix:
        return None, {}

    selected_prefix = min(
        by_prefix.keys(),
        key=lambda p: (_tt_prefix_rank(p), -len(by_prefix[p]), p),
    )
    ordered = {
        label: by_prefix[selected_prefix][label]
        for label in PHYSICAL_TT_RATE_LABELS
        if label in by_prefix[selected_prefix]
    }
    return selected_prefix, ordered


def _merge_step11_physical_tt_columns(
    df: pd.DataFrame,
    *,
    step11_path: Path,
) -> tuple[pd.DataFrame, dict[str, object]]:
    info: dict[str, object] = {
        "enabled": True,
        "source_csv": str(step11_path),
        "selected_prefix": None,
        "selected_columns": [],
        "merge_keys": [],
        "columns_added": [],
    }
    if "filename_base" not in df.columns:
        info["enabled"] = False
        info["reason"] = "filename_base_missing_from_step13_input"
        return df, info
    if not step11_path.exists():
        info["enabled"] = False
        info["reason"] = "step11_collected_csv_missing"
        return df, info

    header = pd.read_csv(step11_path, nrows=0)
    source_columns = [str(c) for c in header.columns]
    merge_keys = [c for c in ("filename_base", "task_id") if c in df.columns and c in source_columns]
    if "filename_base" not in merge_keys:
        info["enabled"] = False
        info["reason"] = "filename_base_missing_from_step11_source"
        return df, info
    info["merge_keys"] = merge_keys

    selected_prefix, tt_cols_by_label = _resolve_physical_tt_rate_columns_from_names(source_columns)
    selected_cols = list(tt_cols_by_label.values())
    info["selected_prefix"] = selected_prefix
    info["selected_columns"] = selected_cols
    if not selected_cols:
        info["enabled"] = False
        info["reason"] = "no_physical_tt_rate_columns_found_in_step11"
        return df, info

    usecols = list(dict.fromkeys(merge_keys + selected_cols))
    step11_df = pd.read_csv(step11_path, usecols=usecols, low_memory=False)
    step11_df = step11_df.drop_duplicates(subset=merge_keys, keep="last")
    cols_to_add = [c for c in selected_cols if c in step11_df.columns and c not in df.columns]
    info["columns_added"] = cols_to_add
    if not cols_to_add:
        info["reason"] = "selected_tt_rate_columns_already_present"
        return df, info

    merged = df.merge(step11_df[merge_keys + cols_to_add], on=merge_keys, how="left")
    return merged, info


def _resolve_group_column(df: pd.DataFrame, raw: object) -> str | None:
    if isinstance(raw, str):
        text = raw.strip()
        if text and text.lower() != "auto" and text in df.columns:
            return text
    for col in ("param_set_id", "param_hash_x"):
        if col in df.columns:
            return col
    return None


def _compute_efficiency_fit_and_relerr(
    df: pd.DataFrame,
    *,
    poly_order: int = 4,
    eps: float = 1e-12,
    clip_fit_output: bool = True,
) -> tuple[pd.DataFrame, list[str], list[str], dict[str, dict[str, object]]]:
    out = df.copy()
    relerr_cols_raw: list[str] = []
    relerr_cols_fit: list[str] = []
    fit_models: dict[str, dict[str, object]] = {}

    for plane in (1, 2, 3, 4):
        emp_col = f"eff_empirical_{plane}"
        sim_col = f"eff_sim_{plane}"
        raw_rel_col = f"relerr_eff_{plane}_pct"
        fitline_col = f"eff_fitline_{plane}"
        fit_rel_col = f"relerr_eff_{plane}_fit_pct"
        fit_abs_rel_col = f"abs_relerr_eff_{plane}_fit_pct"

        if emp_col not in out.columns or sim_col not in out.columns:
            continue

        emp = pd.to_numeric(out[emp_col], errors="coerce")
        sim = pd.to_numeric(out[sim_col], errors="coerce")
        valid = emp.notna() & sim.notna()
        denom = sim.abs().where(sim.abs() > eps, np.nan)

        out[raw_rel_col] = ((emp - sim).abs() / denom) * 100.0
        relerr_cols_raw.append(raw_rel_col)

        model_key = f"plane_{plane}"
        model: dict[str, object] = {
            "plane": plane,
            "status": "missing",
            "empirical_col": emp_col,
            "simulated_col": sim_col,
            "order_requested": int(poly_order),
        }

        if int(valid.sum()) < 2:
            out[fitline_col] = np.nan
            out[fit_rel_col] = np.nan
            out[fit_abs_rel_col] = np.nan
            fit_models[model_key] = model
            continue

        xv = emp.loc[valid].to_numpy(dtype=float)
        yv = sim.loc[valid].to_numpy(dtype=float)

        degree = max(1, min(int(poly_order), len(xv) - 1))
        coeffs: np.ndarray | None = None
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                coeffs = np.polyfit(xv, yv, degree)
        except Exception:
            coeffs = None

        if coeffs is None:
            out[fitline_col] = np.nan
            out[fit_rel_col] = np.nan
            out[fit_abs_rel_col] = np.nan
            model["status"] = "fit_failed"
            model["order_used"] = int(degree)
            fit_models[model_key] = model
            continue

        pred = np.full(len(out), np.nan, dtype=float)
        emp_all = emp.to_numpy(dtype=float)
        finite_emp = np.isfinite(emp_all)
        if finite_emp.any():
            pred_vals = np.polyval(coeffs, emp_all[finite_emp])
            if clip_fit_output:
                pred_vals = np.clip(pred_vals, 0.0, 1.0)
            pred[finite_emp] = pred_vals

        out[fitline_col] = pred
        fit_pred = pd.to_numeric(out[fitline_col], errors="coerce")
        fit_rel = ((fit_pred - sim).abs() / denom) * 100.0
        out[fit_rel_col] = fit_rel
        out[fit_abs_rel_col] = fit_rel.abs()
        relerr_cols_fit.append(fit_rel_col)

        y_pred_valid = np.polyval(coeffs, xv)
        if clip_fit_output:
            y_pred_valid = np.clip(y_pred_valid, 0.0, 1.0)
        ss_res = float(np.sum((yv - y_pred_valid) ** 2))
        ss_tot = float(np.sum((yv - float(np.mean(yv))) ** 2))
        r2 = float("nan") if ss_tot <= 0.0 else (1.0 - ss_res / ss_tot)

        model.update(
            {
                "status": "ok",
                "order_used": int(degree),
                "coefficients_desc": [float(c) for c in coeffs.tolist()],
                "n_points": int(len(xv)),
                "empirical_min": float(np.nanmin(xv)),
                "empirical_max": float(np.nanmax(xv)),
                "r2": float(r2),
                "clip_fit_output": bool(clip_fit_output),
            }
        )
        fit_models[model_key] = model

    return out, relerr_cols_raw, relerr_cols_fit, fit_models


def _split_holdout(
    df: pd.DataFrame,
    *,
    holdout_fraction: float,
    random_seed: int,
    group_col: str | None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    rng = np.random.default_rng(random_seed)
    frac = float(np.clip(holdout_fraction, 0.0, 0.9))
    if frac <= 0.0 or len(df) <= 1:
        return df.copy(), df.iloc[0:0].copy(), {
            "group_column": group_col,
            "holdout_fraction_requested": float(holdout_fraction),
            "holdout_fraction_used": frac,
            "mode": "disabled_or_too_small",
        }

    if group_col is None or group_col not in df.columns:
        mask = rng.random(len(df)) < frac
        if not bool(mask.any()):
            mask[rng.integers(0, len(df))] = True
        if bool(mask.all()):
            mask[rng.integers(0, len(df))] = False
        dset = df.loc[mask].copy()
        dct = df.loc[~mask].copy()
        return dct, dset, {
            "group_column": None,
            "holdout_fraction_requested": float(holdout_fraction),
            "holdout_fraction_used": frac,
            "mode": "row_random",
        }

    work = df.copy()
    g = work[group_col]
    non_na = g.notna()
    groups = pd.Series(g[non_na].unique())
    n_groups = int(len(groups))

    if n_groups <= 1:
        mask = rng.random(len(work)) < frac
        if not bool(mask.any()):
            mask[rng.integers(0, len(work))] = True
        if bool(mask.all()):
            mask[rng.integers(0, len(work))] = False
        dset = work.loc[mask].copy()
        dct = work.loc[~mask].copy()
        return dct, dset, {
            "group_column": group_col,
            "holdout_fraction_requested": float(holdout_fraction),
            "holdout_fraction_used": frac,
            "mode": "row_random_group_degenerate",
            "n_groups": n_groups,
        }

    n_holdout = int(round(frac * n_groups))
    n_holdout = max(1, min(n_holdout, n_groups - 1))
    holdout_groups = set(rng.choice(groups.to_numpy(), size=n_holdout, replace=False).tolist())
    mask = work[group_col].isin(holdout_groups)

    # For NaN groups, fallback to row-random assignment.
    na_idx = np.flatnonzero(~non_na.to_numpy())
    if len(na_idx) > 0:
        na_mask = rng.random(len(na_idx)) < frac
        mask.iloc[na_idx] = na_mask

    dset = work.loc[mask].copy()
    dct = work.loc[~mask].copy()
    if dset.empty and len(work) > 1:
        pick = rng.integers(0, len(work))
        dset = work.iloc[[pick]].copy()
        dct = work.drop(work.index[pick]).copy()
    if dct.empty and len(work) > 1:
        pick = rng.integers(0, len(work))
        dct = work.iloc[[pick]].copy()
        dset = work.drop(work.index[pick]).copy()

    return dct, dset, {
        "group_column": group_col,
        "holdout_fraction_requested": float(holdout_fraction),
        "holdout_fraction_used": frac,
        "mode": "group_split",
        "n_groups_total": n_groups,
        "n_groups_holdout": int(n_holdout),
    }


def _as_float_or_none(raw: object) -> float | None:
    if raw in (None, "", "null", "None"):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _apply_dictionary_quality_filters(
    dictionary_pool: pd.DataFrame,
    *,
    cfg_13: dict,
    cfg_12: dict,
    events_col: str | None,
    relerr_cols: list[str],
) -> tuple[pd.DataFrame, dict]:
    work = dictionary_pool.copy()
    report: dict = {
        "rows_in": int(len(work)),
        "rows_removed": 0,
        "rows_out": 0,
        "filters": {},
    }

    if work.empty:
        report["rows_out"] = 0
        return work, report

    # 1) Minimum event count (dictionary-only strict cut)
    min_events_raw = cfg_13.get("dictionary_min_events", cfg_12.get("dictionary_min_events", 150000))
    try:
        min_events = int(min_events_raw)
    except (TypeError, ValueError):
        min_events = 150000

    if events_col is not None and min_events > 0:
        ev = pd.to_numeric(work[events_col], errors="coerce")
        keep = ev >= float(min_events)
        removed = int((~keep).sum())
        work = work.loc[keep].copy()
    else:
        removed = 0
    report["filters"]["min_events"] = {
        "enabled": bool(events_col is not None and min_events > 0),
        "events_column": events_col,
        "min_events": int(min_events),
        "rows_removed": int(removed),
    }

    # 2) Efficiency relative-error cuts per plane (prefer polynomial-fit relerr)
    relerr_thresholds: dict[str, float] = {}
    relerr_modes: dict[str, str] = {}
    for plane in (1, 2, 3, 4):
        k13_fit = f"dictionary_relerr_eff_{plane}_fit_max_pct"
        k13 = f"dictionary_relerr_eff_{plane}_max_pct"
        k12 = f"dictionary_relerr_eff_{plane}_fit_max_pct"
        thr = _as_float_or_none(cfg_13.get(k13_fit, cfg_13.get(k13, cfg_12.get(k12, 25.0))))
        if thr is not None and thr >= 0.0:
            fit_col = f"relerr_eff_{plane}_fit_pct"
            raw_col = f"relerr_eff_{plane}_pct"
            if fit_col in work.columns:
                relerr_thresholds[fit_col] = thr
                relerr_modes[f"plane_{plane}"] = "fit"
            elif raw_col in work.columns:
                relerr_thresholds[raw_col] = thr
                relerr_modes[f"plane_{plane}"] = "raw"

    removed_rel = 0
    if relerr_thresholds:
        keep = pd.Series(True, index=work.index)
        for rel_col, thr in relerr_thresholds.items():
            if rel_col not in work.columns:
                continue
            rel = pd.to_numeric(work[rel_col], errors="coerce")
            keep &= rel.notna() & (rel <= float(thr))
        removed_rel = int((~keep).sum())
        work = work.loc[keep].copy()
    report["filters"]["eff_relerr"] = {
        "enabled": bool(relerr_thresholds),
        "thresholds_pct": relerr_thresholds,
        "mode_by_plane": relerr_modes,
        "rows_removed": int(removed_rel),
        "relerr_columns_available": [c for c in relerr_cols if c in dictionary_pool.columns],
    }

    # 3) Simple finite-value sanity checks on key columns
    finite_cols_raw = cfg_13.get(
        "dictionary_require_finite_columns",
        [
            "flux_cm2_min",
            "events_per_second_global_rate",
            "eff_empirical_1",
            "eff_empirical_2",
            "eff_empirical_3",
            "eff_empirical_4",
            "eff_sim_1",
            "eff_sim_2",
            "eff_sim_3",
            "eff_sim_4",
        ],
    )
    finite_cols = [c for c in finite_cols_raw if isinstance(c, str) and c in work.columns]

    removed_finite = 0
    if finite_cols:
        keep = pd.Series(True, index=work.index)
        for col in finite_cols:
            keep &= pd.to_numeric(work[col], errors="coerce").notna()
        removed_finite = int((~keep).sum())
        work = work.loc[keep].copy()

    report["filters"]["finite_columns"] = {
        "enabled": bool(finite_cols),
        "columns": finite_cols,
        "rows_removed": int(removed_finite),
    }

    # 4) Optional positive global-rate sanity check
    require_pos_rate = bool(cfg_13.get("dictionary_require_positive_global_rate", True))
    removed_rate = 0
    if require_pos_rate and "events_per_second_global_rate" in work.columns:
        rate = pd.to_numeric(work["events_per_second_global_rate"], errors="coerce")
        keep = rate.notna() & (rate > 0.0)
        removed_rate = int((~keep).sum())
        work = work.loc[keep].copy()

    report["filters"]["positive_global_rate"] = {
        "enabled": require_pos_rate,
        "rows_removed": int(removed_rate),
    }

    report["rows_out"] = int(len(work))
    report["rows_removed"] = int(report["rows_in"] - report["rows_out"])
    return work, report


def _default_selected_feature_columns(
    df: pd.DataFrame,
    *,
    base_columns: Sequence[str] | None = None,
) -> list[str]:
    exclude: set[str] = {
        "filename_base",
        "task_id",
        "param_hash_x",
        "param_set_id",
        "cos_n",
        "flux_cm2_min",
        "z_plane_1",
        "z_plane_2",
        "z_plane_3",
        "z_plane_4",
        "eff_p1",
        "eff_p2",
        "eff_p3",
        "eff_p4",
        "eff_sim_1",
        "eff_sim_2",
        "eff_sim_3",
        "eff_sim_4",
        "selected_rows",
        "requested_rows",
        "generated_events_count",
        "num_events",
        "event_count",
        "n_events",
    }
    source_cols = list(base_columns) if base_columns is not None else list(df.columns)
    cols = [
        c
        for c in source_cols
        if c not in exclude
        and not str(c).startswith("events_per_second_global_rate")
        and not c.startswith("relerr_eff_")
        and not c.startswith("abs_relerr_eff_")
        and not c.startswith("eff_fitline_")
    ]
    return cols


def _build_selected_feature_columns(
    df: pd.DataFrame,
    *,
    feature_space_cfg: dict | None,
    feature_manifest: dict | None = None,
) -> tuple[list[str], dict]:
    manifest_primary = manifest_primary_feature_columns(
        feature_manifest or {},
        available_columns=list(df.columns),
    )
    keep_dimensions = manifest_primary or extract_feature_dimensions(feature_space_cfg)
    fallback = (
        _default_selected_feature_columns(df, base_columns=keep_dimensions)
        if keep_dimensions
        else _default_selected_feature_columns(df)
    )
    selected, info = resolve_selected_feature_space_columns(
        available_columns=list(df.columns),
        feature_space_cfg=feature_space_cfg or {},
        fallback_columns=fallback,
    )
    info = dict(info)
    info["feature_manifest_loaded"] = bool(feature_manifest)
    info["feature_manifest_primary_columns"] = manifest_primary
    if manifest_primary and info.get("source") == "fallback_columns":
        info["source"] = "step_1_2.feature_space_manifest.primary_feature_columns"
    return selected, info


def _plot_split_counts(n_total: int, n_dict_pool: int, n_dict_final: int, n_dataset: int) -> None:
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    names = ["Input", "Dictionary pool", "Dictionary final", "Holdout dataset"]
    vals = [n_total, n_dict_pool, n_dict_final, n_dataset]
    ax.bar(names, vals, color=["#8DA0CB", "#66C2A5", "#1B9E77", "#FC8D62"], alpha=0.9)
    for i, v in enumerate(vals):
        ax.text(i, v, f"{v}", ha="center", va="bottom", fontsize=9)
    ax.set_ylabel("Rows")
    ax.set_title("STEP 1.3 split and quality filtering")
    ax.grid(True, axis="y", alpha=0.2)
    fig.tight_layout()
    _save_figure(fig, PLOTS_DIR / "split_counts.png", dpi=150)
    plt.close(fig)


def _plot_events_hist(df_dict: pd.DataFrame, df_data: pd.DataFrame, events_col: str | None) -> None:
    if events_col is None:
        return
    ev_d = pd.to_numeric(df_dict.get(events_col), errors="coerce").dropna()
    ev_t = pd.to_numeric(df_data.get(events_col), errors="coerce").dropna()
    if ev_d.empty and ev_t.empty:
        return
    fig, ax = plt.subplots(figsize=(8.0, 4.8))
    if not ev_d.empty:
        ax.hist(ev_d, bins=40, alpha=0.55, color="#1B9E77", label="Dictionary")
    if not ev_t.empty:
        ax.hist(ev_t, bins=40, alpha=0.45, color="#FC8D62", label="Holdout dataset")
    ax.set_xlabel(events_col)
    ax.set_ylabel("Files")
    ax.set_title("Event-count distributions after split")
    ax.legend()
    ax.grid(True, alpha=0.2)
    fig.tight_layout()
    _save_figure(fig, PLOTS_DIR / "event_count_distributions.png", dpi=150)
    plt.close(fig)


def _split_dictionary_non_dictionary(
    all_rows: pd.DataFrame,
    dictionary_index: set[int],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    is_dict = all_rows.index.isin(dictionary_index)
    non_dict = all_rows.loc[~is_dict].copy()
    only_dict = all_rows.loc[is_dict].copy()
    return non_dict, only_dict


def _format_poly_label(coeffs_desc: list[float]) -> str:
    if not coeffs_desc:
        return "fit unavailable"
    degree = len(coeffs_desc) - 1
    parts: list[str] = []
    for i, coef in enumerate(coeffs_desc):
        power = degree - i
        if power > 1:
            parts.append(f"{coef:+.3f}x^{power}")
        elif power == 1:
            parts.append(f"{coef:+.3f}x")
        else:
            parts.append(f"{coef:+.3f}")
    return " ".join(parts)


def _tight_unit_interval_bounds(
    *arrays: pd.Series | np.ndarray,
    pad_fraction: float = 0.08,
    min_pad: float = 0.02,
) -> tuple[float, float]:
    finite_chunks: list[np.ndarray] = []
    for arr in arrays:
        vals = np.asarray(arr, dtype=float).ravel()
        if vals.size == 0:
            continue
        mask = np.isfinite(vals)
        if np.any(mask):
            finite_chunks.append(vals[mask])
    if not finite_chunks:
        return 0.0, 1.0

    data = np.concatenate(finite_chunks)
    lo = float(np.nanmin(data))
    hi = float(np.nanmax(data))
    if not np.isfinite(lo) or not np.isfinite(hi):
        return 0.0, 1.0

    span = hi - lo
    pad = max(float(min_pad), float(span * pad_fraction)) if span > 0.0 else float(min_pad)
    lo = max(0.0, lo - pad)
    hi = min(1.0, hi + pad)
    if hi <= lo:
        return 0.0, 1.0
    return lo, hi


def _plot_relerr_hist(
    all_rows: pd.DataFrame,
    *,
    dictionary_index: set[int],
) -> None:
    non_dict, only_dict = _split_dictionary_non_dictionary(all_rows, dictionary_index)
    fig, axes = plt.subplots(2, 2, figsize=(11.0, 8.5))
    axes = axes.flatten()

    for i, plane in enumerate((1, 2, 3, 4)):
        ax = axes[i]
        fit_col = f"relerr_eff_{plane}_fit_pct"
        raw_col = f"relerr_eff_{plane}_pct"
        col = fit_col if fit_col in all_rows.columns else raw_col
        if col not in all_rows.columns:
            ax.set_visible(False)
            continue

        vals_non = pd.to_numeric(non_dict[col], errors="coerce").dropna()
        vals_dic = pd.to_numeric(only_dict[col], errors="coerce").dropna()
        if vals_non.empty and vals_dic.empty:
            ax.set_visible(False)
            continue

        combined = pd.concat([vals_non, vals_dic], ignore_index=True)
        x_hi = float(np.nanpercentile(combined.to_numpy(dtype=float), 99.5))
        if not np.isfinite(x_hi) or x_hi <= 0.0:
            x_hi = float(np.nanmax(combined.to_numpy(dtype=float)))
        if not np.isfinite(x_hi) or x_hi <= 0.0:
            x_hi = 1.0
        x_hi = max(1.0, x_hi)
        bins = np.linspace(0.0, x_hi, 36)

        if not vals_non.empty:
            ax.hist(vals_non, bins=bins, alpha=0.45, color="#8E8E8E", label="Non-dictionary", density=False)
        if not vals_dic.empty:
            ax.hist(vals_dic, bins=bins, alpha=0.55, color="#D7301F", label="Dictionary", density=False)

        med_non = float(np.nanmedian(vals_non.to_numpy(dtype=float))) if not vals_non.empty else float("nan")
        med_dic = float(np.nanmedian(vals_dic.to_numpy(dtype=float))) if not vals_dic.empty else float("nan")
        ax.set_xlim(0.0, x_hi)
        ax.set_xlabel("Relative error [%]")
        ax.set_ylabel("Rows")
        ax.set_title(
            f"Plane {plane} ({'fit' if col == fit_col else 'raw'})\n"
            f"median non-dict={med_non:.2f}, dict={med_dic:.2f}",
            fontsize=9,
        )
        ax.grid(True, alpha=0.2)
        if plane == 1:
            ax.legend(fontsize=8, loc="upper right")

    fig.suptitle("Efficiency relative error by plane (dictionary vs non-dictionary)", fontsize=11)
    fig.tight_layout(rect=[0, 0.01, 1, 0.97])
    _save_figure(fig, PLOTS_DIR / "eff_relerr_histograms.png", dpi=150)
    plt.close(fig)


def _plot_relerr_report(
    all_rows: pd.DataFrame,
    *,
    dictionary_index: set[int],
    fit_models: dict[str, dict[str, object]],
    cfg_13: dict,
    cfg_12: dict,
) -> None:
    non_dict, only_dict = _split_dictionary_non_dictionary(all_rows, dictionary_index)
    fig, axes = plt.subplots(4, 3, figsize=(15.0, 15.5))

    for plane in (1, 2, 3, 4):
        row = plane - 1
        ax_scatter = axes[row, 0]
        ax_rel = axes[row, 1]
        ax_hist = axes[row, 2]

        emp_col = f"eff_empirical_{plane}"
        sim_col = f"eff_sim_{plane}"
        fit_col = f"eff_fitline_{plane}"
        rel_fit_col = f"relerr_eff_{plane}_fit_pct"
        rel_raw_col = f"relerr_eff_{plane}_pct"
        rel_col = rel_fit_col if rel_fit_col in all_rows.columns else rel_raw_col

        if emp_col not in all_rows.columns or sim_col not in all_rows.columns or rel_col not in all_rows.columns:
            ax_scatter.set_visible(False)
            ax_rel.set_visible(False)
            ax_hist.set_visible(False)
            continue

        x_non = pd.to_numeric(non_dict[emp_col], errors="coerce")
        y_non = pd.to_numeric(non_dict[sim_col], errors="coerce")
        m_non = x_non.notna() & y_non.notna()
        if m_non.any():
            ax_scatter.scatter(
                x_non[m_non], y_non[m_non], s=7, alpha=0.22, color="#8E8E8E", edgecolors="none", label="Non-dictionary"
            )

        x_dic = pd.to_numeric(only_dict[emp_col], errors="coerce")
        y_dic = pd.to_numeric(only_dict[sim_col], errors="coerce")
        m_dic = x_dic.notna() & y_dic.notna()
        if m_dic.any():
            ax_scatter.scatter(
                x_dic[m_dic], y_dic[m_dic], s=20, alpha=0.8, marker="x", color="#D7301F", linewidths=0.9, label="Dictionary"
            )

        fit_x = np.array([], dtype=float)
        fit_y = np.array([], dtype=float)

        if fit_col in all_rows.columns:
            model_key = f"plane_{plane}"
            model = fit_models.get(model_key, {})
            coeffs = model.get("coefficients_desc", [])
            if isinstance(coeffs, list) and coeffs:
                emp_lo = _as_float_or_none(model.get("empirical_min"))
                emp_hi = _as_float_or_none(model.get("empirical_max"))
                if emp_lo is None or emp_hi is None or not np.isfinite(emp_lo) or not np.isfinite(emp_hi):
                    emp_lo, emp_hi = _tight_unit_interval_bounds(x_non[m_non], x_dic[m_dic])
                if emp_hi < emp_lo:
                    emp_lo, emp_hi = emp_hi, emp_lo
                fit_x = np.linspace(float(emp_lo), float(emp_hi), 200)
                fit_y = np.polyval(np.asarray(coeffs, dtype=float), fit_x)
                fit_y = np.clip(fit_y, 0.0, 1.0)
                ax_scatter.plot(fit_x, fit_y, color="#1F78B4", linewidth=1.7, label="Polynomial fit")
            if plane == 1 and isinstance(coeffs, list) and coeffs:
                ax_scatter.text(
                    0.03,
                    0.97,
                    _format_poly_label([float(c) for c in coeffs]),
                    transform=ax_scatter.transAxes,
                    ha="left",
                    va="top",
                    fontsize=7,
                    bbox={"facecolor": "white", "alpha": 0.75, "edgecolor": "none"},
                )

        xy_lo, xy_hi = _tight_unit_interval_bounds(
            x_non[m_non],
            y_non[m_non],
            x_dic[m_dic],
            y_dic[m_dic],
            fit_x,
            fit_y,
        )
        ax_scatter.plot([xy_lo, xy_hi], [xy_lo, xy_hi], color="black", linestyle="--", linewidth=1.0)
        ax_scatter.set_xlim(xy_lo, xy_hi)
        ax_scatter.set_ylim(xy_lo, xy_hi)
        ax_scatter.set_aspect("equal", adjustable="box")
        ax_scatter.set_xlabel("Empirical efficiency")
        ax_scatter.set_ylabel("Simulated efficiency")
        ax_scatter.set_title(f"Plane {plane}: empirical vs simulated")
        ax_scatter.grid(True, alpha=0.2)
        if plane == 1:
            ax_scatter.legend(fontsize=7, loc="lower right")

        rel_non = pd.to_numeric(non_dict[rel_col], errors="coerce")
        rel_dic = pd.to_numeric(only_dict[rel_col], errors="coerce")
        relx_non = pd.to_numeric(non_dict[sim_col], errors="coerce")
        relx_dic = pd.to_numeric(only_dict[sim_col], errors="coerce")
        relm_non = relx_non.notna() & rel_non.notna()
        relm_dic = relx_dic.notna() & rel_dic.notna()
        if relm_non.any():
            ax_rel.scatter(
                relx_non[relm_non], rel_non[relm_non], s=7, alpha=0.2, color="#8E8E8E", edgecolors="none", label="Non-dictionary"
            )
        if relm_dic.any():
            ax_rel.scatter(
                relx_dic[relm_dic], rel_dic[relm_dic], s=20, alpha=0.75, marker="x", color="#D7301F", linewidths=0.9, label="Dictionary"
            )

        thr = _as_float_or_none(
            cfg_13.get(
                f"dictionary_relerr_eff_{plane}_fit_max_pct",
                cfg_13.get(f"dictionary_relerr_eff_{plane}_max_pct", cfg_12.get(f"dictionary_relerr_eff_{plane}_fit_max_pct", 25.0)),
            )
        )
        if thr is not None and thr >= 0.0:
            ax_rel.axhline(float(thr), color="#1F78B4", linestyle="--", linewidth=1.2)

        rel_vals = pd.concat([rel_non.dropna(), rel_dic.dropna()], ignore_index=True)
        rel_hi = float(np.nanpercentile(rel_vals.to_numpy(dtype=float), 99.5)) if not rel_vals.empty else 1.0
        if not np.isfinite(rel_hi) or rel_hi <= 0.0:
            rel_hi = 1.0
        ax_rel.set_ylim(0.0, max(rel_hi, 1.0))
        rel_x_lo, rel_x_hi = _tight_unit_interval_bounds(relx_non[relm_non], relx_dic[relm_dic], fit_y)
        ax_rel.set_xlim(rel_x_lo, rel_x_hi)
        ax_rel.set_xlabel("Simulated efficiency")
        ax_rel.set_ylabel("Relative error [%]")
        ax_rel.set_title(f"Plane {plane}: relerr vs simulated ({'fit' if rel_col == rel_fit_col else 'raw'})")
        ax_rel.grid(True, alpha=0.2)
        if plane == 1:
            ax_rel.legend(fontsize=7, loc="upper left")

        bins_hi = max(1.0, rel_hi)
        bins = np.linspace(0.0, bins_hi, 34)
        if not rel_non.dropna().empty:
            ax_hist.hist(rel_non.dropna(), bins=bins, alpha=0.45, color="#8E8E8E", label="Non-dictionary")
        if not rel_dic.dropna().empty:
            ax_hist.hist(rel_dic.dropna(), bins=bins, alpha=0.55, color="#D7301F", label="Dictionary")

        med_non = float(np.nanmedian(rel_non.to_numpy(dtype=float))) if rel_non.notna().any() else float("nan")
        med_dic = float(np.nanmedian(rel_dic.to_numpy(dtype=float))) if rel_dic.notna().any() else float("nan")
        ax_hist.set_xlim(0.0, bins_hi)
        ax_hist.set_xlabel("Relative error [%]")
        ax_hist.set_ylabel("Rows")
        ax_hist.set_title(f"Plane {plane}: histogram\nmedian non={med_non:.2f}, dict={med_dic:.2f}", fontsize=9)
        ax_hist.grid(True, alpha=0.2)
        if plane == 1:
            ax_hist.legend(fontsize=7, loc="upper right")

    fig.suptitle("Efficiency fit relative-error report", fontsize=12)
    fig.tight_layout(rect=[0, 0.01, 1, 0.985])
    _save_figure(fig, PLOTS_DIR / "relerr_eff_report.png", dpi=150)
    plt.close(fig)


def _resolve_plot_parameter_columns(config: dict, dictionary: pd.DataFrame) -> list[str]:
    raw = config.get("plot_parameters", [])
    out: list[str] = []
    if isinstance(raw, (list, tuple)):
        for col in raw:
            if isinstance(col, str) and col in dictionary.columns:
                out.append(col)
    if not out:
        fallback = [
            "flux_cm2_min",
            "eff_sim_1",
            "eff_sim_2",
            "eff_sim_3",
            "eff_sim_4",
            "cos_n",
        ]
        out = [c for c in fallback if c in dictionary.columns]
    return list(dict.fromkeys(out))


def _plot_parameter_scatter_matrix(
    dataset: pd.DataFrame,
    dictionary: pd.DataFrame,
    plot_cols: list[str],
) -> None:
    cols = [c for c in plot_cols if c in dataset.columns]
    if len(cols) < 2:
        return
    n = len(cols)
    fig, axes = plt.subplots(n, n, figsize=(2.8 * n, 2.8 * n))
    for i, cy in enumerate(cols):
        for j, cx in enumerate(cols):
            ax = axes[i, j]
            if i == j:
                d_vals = pd.to_numeric(dataset[cx], errors="coerce").dropna()
                if not d_vals.empty:
                    ax.hist(d_vals, bins=28, alpha=0.5, color="#4C78A8")
                if cx in dictionary.columns:
                    dict_vals = pd.to_numeric(dictionary[cx], errors="coerce").dropna()
                    if not dict_vals.empty:
                        ax.hist(dict_vals, bins=28, alpha=0.6, color="#E45756")
                ax.set_yscale("log")
                ax.set_xlabel(cx, fontsize=7)
            elif i > j:
                dx = pd.to_numeric(dataset[cx], errors="coerce")
                dy = pd.to_numeric(dataset[cy], errors="coerce")
                m = dx.notna() & dy.notna()
                if m.sum() > 0:
                    ax.scatter(dx[m], dy[m], s=5, alpha=0.25, color="#AAAAAA")
                if cx in dictionary.columns and cy in dictionary.columns:
                    ddx = pd.to_numeric(dictionary[cx], errors="coerce")
                    ddy = pd.to_numeric(dictionary[cy], errors="coerce")
                    dm = ddx.notna() & ddy.notna()
                    if dm.sum() > 0:
                        ax.scatter(ddx[dm], ddy[dm], s=14, alpha=0.7, marker="x", color="#E45756", linewidths=0.8)
                ax.set_xlabel(cx, fontsize=7)
                ax.set_ylabel(cy, fontsize=7)
            else:
                ax.axis("off")
            ax.tick_params(labelsize=6)
    fig.suptitle("Parameter scatter matrix (grey=data, red×=dictionary)", fontsize=10)
    fig.tight_layout()
    _save_figure(fig, PLOTS_DIR / "parameter_scatter_matrix.png", dpi=150)
    plt.close(fig)


def _normalized_01(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    lo = float(np.nanmin(x))
    hi = float(np.nanmax(x))
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return np.zeros_like(x, dtype=float)
    return (x - lo) / (hi - lo)


def _convex_hull_area(points: np.ndarray) -> float:
    try:
        from scipy.spatial import ConvexHull  # type: ignore
    except Exception:
        return float("nan")
    if points.shape[0] < 3:
        return float("nan")
    try:
        hull = ConvexHull(points)
        return float(hull.volume)  # In 2D, scipy reports area as `volume`.
    except Exception:
        return float("nan")


def _coverage_density_metrics(points: np.ndarray) -> dict[str, float]:
    metrics = {
        "nn50": float("nan"),
        "nn90": float("nan"),
        "r90": float("nan"),
    }
    if points.shape[0] < 2:
        return metrics

    pts = np.asarray(points, dtype=float)
    if pts.shape[0] > 4000:
        rng = np.random.default_rng(42)
        keep = rng.choice(np.arange(pts.shape[0]), size=4000, replace=False)
        pts = pts[keep]

    try:
        diffs = pts[:, None, :] - pts[None, :, :]
        dist2 = np.einsum("ijk,ijk->ij", diffs, diffs)
        np.fill_diagonal(dist2, np.inf)
        nn = np.sqrt(np.nanmin(dist2, axis=1))
        centroid = np.nanmean(pts, axis=0)
        rr = np.sqrt(np.nansum((pts - centroid) ** 2, axis=1))
        metrics["nn50"] = float(np.nanpercentile(nn, 50))
        metrics["nn90"] = float(np.nanpercentile(nn, 90))
        metrics["r90"] = float(np.nanpercentile(rr, 90))
    except Exception:
        return metrics
    return metrics


def _draw_light_density_contour(
    ax: plt.Axes,
    x: np.ndarray,
    y: np.ndarray,
) -> None:
    if x.size < 3 or y.size < 3:
        return
    try:
        h, xe, ye = np.histogram2d(x, y, bins=8, range=[[0, 1], [0, 1]])
        h = h.T.astype(float)
        ax.pcolormesh(xe, ye, h, cmap="turbo", alpha=0.30, zorder=0, shading="flat")
    except Exception:
        return


def _plot_dictionary_coverage_overview(
    dictionary: pd.DataFrame,
    plot_cols: list[str],
) -> None:
    cols = [c for c in plot_cols if c in dictionary.columns]
    if len(cols) < 2:
        return
    n = len(cols)
    fig, axes = plt.subplots(n, n, figsize=(2.8 * n, 2.8 * n), squeeze=False)

    for i, cy in enumerate(cols):
        for j, cx in enumerate(cols):
            ax = axes[i, j]
            if i < j:
                ax.axis("off")
                continue

            if i == j:
                vals = pd.to_numeric(dictionary[cx], errors="coerce").dropna()
                if vals.empty:
                    ax.axis("off")
                    continue
                ax.hist(vals.to_numpy(dtype=float), bins=28, color="#4C78A8", alpha=0.68)
                ax.set_yscale("log")
                if i == n - 1:
                    ax.set_xlabel(cx, fontsize=7)
                else:
                    ax.set_xticklabels([])
                if j == 0:
                    ax.set_ylabel("Rows", fontsize=7)
                else:
                    ax.set_yticklabels([])
                ax.grid(True, alpha=0.2)
                ax.tick_params(labelsize=6)
                continue

            x = pd.to_numeric(dictionary[cx], errors="coerce")
            y = pd.to_numeric(dictionary[cy], errors="coerce")
            m = x.notna() & y.notna()
            if int(m.sum()) < 3:
                ax.text(0.5, 0.5, "Insufficient points", ha="center", va="center", transform=ax.transAxes, fontsize=7)
                ax.set_xlim(0, 1)
                ax.set_ylim(0, 1)
                ax.grid(True, alpha=0.2)
                continue

            xn = _normalized_01(x[m].to_numpy(dtype=float))
            yn = _normalized_01(y[m].to_numpy(dtype=float))
            pts = np.column_stack([xn, yn])
            uniq = np.unique(pts, axis=0)
            if uniq.shape[0] < 3:
                ax.text(0.5, 0.5, "Insufficient unique points", ha="center", va="center", transform=ax.transAxes, fontsize=7)
                ax.set_xlim(0, 1)
                ax.set_ylim(0, 1)
                ax.grid(True, alpha=0.2)
                continue

            _draw_light_density_contour(ax, uniq[:, 0], uniq[:, 1])
            ax.scatter(
                uniq[:, 0],
                uniq[:, 1],
                s=11,
                color="#D7301F",
                alpha=0.38,
                edgecolors="none",
                zorder=2,
            )

            area = _convex_hull_area(uniq) * 100.0
            metrics = _coverage_density_metrics(uniq)
            area_txt = "n/a" if not np.isfinite(area) else f"{area:.1f}%"
            nn50_txt = "n/a" if not np.isfinite(metrics["nn50"]) else f"{metrics['nn50']:.3f}"
            ax.text(
                0.02,
                0.98,
                f"H:{area_txt} NN50:{nn50_txt}",
                transform=ax.transAxes,
                ha="left",
                va="top",
                fontsize=6.2,
                bbox={"facecolor": "white", "alpha": 0.7, "edgecolor": "none"},
            )

            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            ax.set_aspect("equal", adjustable="box")
            if i == n - 1:
                ax.set_xlabel(f"Norm {cx}", fontsize=7)
            else:
                ax.set_xticklabels([])
            if j == 0:
                ax.set_ylabel(f"Norm {cy}", fontsize=7)
            else:
                ax.set_yticklabels([])
            ax.grid(True, alpha=0.16)
            ax.tick_params(labelsize=6)

    fig.suptitle("Dictionary coverage overview (lower-triangle, normalized + light density contours)", fontsize=11)
    fig.tight_layout(rect=(0.0, 0.01, 1.0, 0.965))
    _save_figure(fig, PLOTS_DIR / "dictionary_coverage_overview.png", dpi=150)
    plt.close(fig)


def _plot_eff_sim_vs_empirical(
    all_rows: pd.DataFrame,
    *,
    dictionary_index: set[int],
    fit_models: dict[str, dict[str, object]],
) -> None:
    non_dict, only_dict = _split_dictionary_non_dictionary(all_rows, dictionary_index)
    fig, axes = plt.subplots(2, 2, figsize=(10, 10), sharex=True, sharey=True)
    for plane in range(1, 5):
        ax = axes[(plane - 1) // 2, (plane - 1) % 2]
        sim_col = f"eff_sim_{plane}"
        emp_col = f"eff_empirical_{plane}"
        if sim_col not in all_rows.columns or emp_col not in all_rows.columns:
            ax.set_visible(False)
            continue
        sim_non = pd.to_numeric(non_dict[sim_col], errors="coerce")
        emp_non = pd.to_numeric(non_dict[emp_col], errors="coerce")
        m_non = sim_non.notna() & emp_non.notna()
        if m_non.any():
            ax.scatter(emp_non[m_non], sim_non[m_non], s=8, alpha=0.25, color="#8E8E8E", zorder=2, label="Non-dictionary")

        sim_dic = pd.to_numeric(only_dict[sim_col], errors="coerce")
        emp_dic = pd.to_numeric(only_dict[emp_col], errors="coerce")
        m_dic = sim_dic.notna() & emp_dic.notna()
        if m_dic.any():
            ax.scatter(
                emp_dic[m_dic],
                sim_dic[m_dic],
                s=20,
                alpha=0.8,
                marker="x",
                color="#D7301F",
                linewidths=1.0,
                zorder=3,
                label="Dictionary",
            )

        model = fit_models.get(f"plane_{plane}", {})
        coeffs = model.get("coefficients_desc", [])
        if isinstance(coeffs, list) and coeffs:
            xv = np.linspace(0.0, 1.0, 200)
            yv = np.polyval(np.asarray(coeffs, dtype=float), xv)
            yv = np.clip(yv, 0.0, 1.0)
            ax.plot(xv, yv, color="#1F78B4", linewidth=1.8, label="Polynomial fit")
            r2 = model.get("r2", float("nan"))
            order_used = model.get("order_used", len(coeffs) - 1)
            if isinstance(r2, (float, int)):
                ax.text(
                    0.03,
                    0.97,
                    f"deg={order_used}, R²={float(r2):.3f}\n{_format_poly_label([float(c) for c in coeffs])}",
                    transform=ax.transAxes,
                    ha="left",
                    va="top",
                    fontsize=7,
                    bbox={"facecolor": "white", "alpha": 0.75, "edgecolor": "none"},
                )
        ax.plot([0, 1], [0, 1], "k--", linewidth=1)
        ax.set_xlabel("Empirical efficiency")
        ax.set_ylabel("Simulated efficiency")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.grid(True, alpha=0.25)
        ax.set_title(f"Plane {plane}")
        if plane == 1:
            ax.legend(fontsize=8, loc="lower right")
    fig.suptitle("Empirical vs Simulated Efficiency per Plane", fontsize=11)
    fig.tight_layout()
    _save_figure(fig, PLOTS_DIR / "scatter_eff_sim_vs_estimated.png", dpi=150)
    plt.close(fig)


def _plot_empirical_eff2_vs_eff3(dataset: pd.DataFrame, dictionary: pd.DataFrame) -> None:
    x_col = "eff_empirical_2"
    y_col = "eff_empirical_3"
    if x_col not in dataset.columns or y_col not in dataset.columns:
        return
    x = pd.to_numeric(dataset[x_col], errors="coerce")
    y = pd.to_numeric(dataset[y_col], errors="coerce")
    m = x.notna() & y.notna()
    if m.sum() == 0:
        return
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.scatter(x[m], y[m], s=10, alpha=0.35, color="#AAAAAA", label="Dataset")
    if x_col in dictionary.columns and y_col in dictionary.columns:
        dx = pd.to_numeric(dictionary[x_col], errors="coerce")
        dy = pd.to_numeric(dictionary[y_col], errors="coerce")
        dm = dx.notna() & dy.notna()
        if dm.any():
            ax.scatter(dx[dm], dy[dm], s=24, alpha=0.85, marker="x", color="#E45756", linewidths=1.0, label="Dictionary")
    ax.plot([0, 1], [0, 1], "k--", linewidth=1, label="y=x")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("Empirical efficiency (plane 2)")
    ax.set_ylabel("Empirical efficiency (plane 3)")
    ax.set_title("Empirical Efficiency: Plane 2 vs Plane 3")
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=8, loc="lower right")
    fig.tight_layout()
    _save_figure(fig, PLOTS_DIR / "scatter_empirical_eff2_vs_eff3.png", dpi=150)
    plt.close(fig)





def main() -> int:
    parser = argparse.ArgumentParser(
        description="STEP 1.3: Build dictionary and holdout dataset from transformed feature space."
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--input-csv", default=None)
    args = parser.parse_args()

    config = _load_config(Path(args.config))
    _clear_plots_dir()

    cfg_12 = config.get("step_1_2", {}) if isinstance(config, dict) else {}
    cfg_13 = config.get("step_1_3", {}) if isinstance(config, dict) else {}
    feature_space_config_path = resolve_feature_space_config_path(
        PIPELINE_DIR,
        config=config,
        step_cfg=cfg_12 if isinstance(cfg_12, dict) else {},
    )
    feature_space_all = load_feature_space_config(feature_space_config_path)
    feature_space_cfg = (
        feature_space_all.get("step_1_2", {})
        if isinstance(feature_space_all.get("step_1_2", {}), dict)
        else {}
    )
    feature_manifest = load_step1_feature_manifest(DEFAULT_STEP12_MANIFEST)

    input_cfg = cfg_13.get("input_csv") if isinstance(cfg_13, dict) else None
    if args.input_csv:
        input_path = Path(args.input_csv).expanduser()
    elif input_cfg not in (None, "", "null", "None"):
        input_path = Path(str(input_cfg)).expanduser()
    else:
        input_path = DEFAULT_INPUT
    if not input_path.exists():
        log.error("Input CSV not found: %s", input_path)
        return 1

    log.info("Loading transformed feature space: %s", input_path)
    df = pd.read_csv(input_path, low_memory=False)
    log.info("  Rows loaded: %d, columns=%d", len(df), len(df.columns))
    if df.empty:
        log.error("Input transformed feature space is empty.")
        return 1

    df, tt_passthrough_info = _merge_step11_physical_tt_columns(
        df,
        step11_path=DEFAULT_STEP11_COLLECTED,
    )
    if tt_passthrough_info.get("enabled"):
        log.info(
            "Merged STEP 1.1 physical TT-rate passthrough: prefix=%s added=%d columns.",
            str(tt_passthrough_info.get("selected_prefix")),
            int(len(tt_passthrough_info.get("columns_added", []))),
        )
    else:
        log.warning(
            "STEP 1.1 physical TT-rate passthrough disabled: %s.",
            str(tt_passthrough_info.get("reason")),
        )

    try:
        poly_order = int(cfg_12.get("eff_fit_polynomial_order", 4))
    except (TypeError, ValueError):
        poly_order = 4
    poly_order = max(1, poly_order)

    work, relerr_cols_raw, relerr_cols_fit, fit_models = _compute_efficiency_fit_and_relerr(
        df,
        poly_order=poly_order,
        clip_fit_output=True,
    )
    relerr_cols = list(dict.fromkeys(relerr_cols_fit + relerr_cols_raw))

    group_col = _resolve_group_column(work, cfg_13.get("split_group_column", "auto"))
    try:
        holdout_fraction = float(cfg_13.get("dataset_holdout_fraction", 0.20))
    except (TypeError, ValueError):
        holdout_fraction = 0.20
    holdout_fraction = float(np.clip(holdout_fraction, 0.0, 0.9))

    try:
        split_seed = int(cfg_13.get("split_random_seed", 42))
    except (TypeError, ValueError):
        split_seed = 42

    dictionary_pool, dataset, split_report = _split_holdout(
        work,
        holdout_fraction=holdout_fraction,
        random_seed=split_seed,
        group_col=group_col,
    )

    events_col = _resolve_events_column(work)
    dictionary, quality_report = _apply_dictionary_quality_filters(
        dictionary_pool,
        cfg_13=cfg_13,
        cfg_12=cfg_12,
        events_col=events_col,
        relerr_cols=relerr_cols,
    )

    # Deduplicate: keep one representative row per unique parameter vector.
    # Among duplicates, keep the row with the most statistics (highest event count).
    param_dedup_cols = [c for c in ("flux_cm2_min", "eff_sim_1", "eff_sim_2", "eff_sim_3", "eff_sim_4") if c in dictionary.columns]
    n_before_dedup = len(dictionary)
    if param_dedup_cols:
        if events_col and events_col in dictionary.columns:
            sort_col = pd.to_numeric(dictionary[events_col], errors="coerce").fillna(0)
            dictionary = dictionary.loc[sort_col.groupby(
                [dictionary[c] for c in param_dedup_cols]
            ).idxmax().values]
        else:
            dictionary = dictionary.drop_duplicates(subset=param_dedup_cols, keep="first")
        n_after_dedup = len(dictionary)
        log.info(
            "Deduplicated dictionary by parameter vector (%s): %d -> %d rows (removed %d duplicates).",
            param_dedup_cols, n_before_dedup, n_after_dedup, n_before_dedup - n_after_dedup,
        )

    dictionary_index = set(int(i) for i in dictionary.index.to_numpy())
    dictionary = dictionary.reset_index(drop=True)
    dataset = dataset.reset_index(drop=True)

    if dictionary.empty:
        log.error("Dictionary is empty after STEP 1.3 quality filters.")
        return 1
    if dataset.empty:
        log.warning("Holdout dataset is empty after split. Validation will be disabled downstream.")

    selected_feature_columns, selected_feature_info = _build_selected_feature_columns(
        dictionary,
        feature_space_cfg=feature_space_cfg,
        feature_manifest=feature_manifest,
    )
    if not selected_feature_columns:
        log.error("No selected feature columns resolved for STEP 1.3.")
        return 1

    dictionary_path = FILES_DIR / "dictionary.csv"
    dataset_path = FILES_DIR / "dataset.csv"
    selected_features_path = FILES_DIR / "selected_feature_columns.json"
    summary_path = FILES_DIR / "build_summary.json"

    dictionary.to_csv(dictionary_path, index=False)
    dataset.to_csv(dataset_path, index=False)
    selected_features_payload = {
        "selected_feature_columns": selected_feature_columns,
        "selection_strategy": str(selected_feature_info.get("source", "step_1_3_simple_features_v1")),
        "selection_report": {
            "source": str(selected_feature_info.get("source", "all_non_parameter_columns_from_step_1_3_dictionary")),
            "selected_feature_count": int(len(selected_feature_columns)),
            "feature_space_config_path": str(feature_space_config_path),
            "feature_space_config_loaded": bool(feature_space_cfg),
            "feature_space_manifest_json": str(DEFAULT_STEP12_MANIFEST),
            "feature_space_manifest_loaded": bool(feature_manifest),
            "used_feature_space_config": bool(selected_feature_info.get("used_feature_space_config", False)),
            "include_patterns": selected_feature_info.get("include_patterns", []),
            "exclude_patterns": selected_feature_info.get("exclude_patterns", []),
            "unmatched_include_patterns": selected_feature_info.get("unmatched_include_patterns", []),
            "unmatched_exclude_patterns": selected_feature_info.get("unmatched_exclude_patterns", []),
        },
    }
    selected_features_path.write_text(json.dumps(selected_features_payload, indent=2), encoding="utf-8")

    _plot_split_counts(len(work), len(dictionary_pool), len(dictionary), len(dataset))
    _plot_events_hist(dictionary, dataset, events_col)
    _plot_relerr_report(work, dictionary_index=dictionary_index, fit_models=fit_models, cfg_13=cfg_13, cfg_12=cfg_12)
    plot_cols = _resolve_plot_parameter_columns(config, dictionary)
    _plot_parameter_scatter_matrix(dataset, dictionary, plot_cols)
    _plot_dictionary_coverage_overview(dictionary, plot_cols)
    _plot_empirical_eff2_vs_eff3(dataset, dictionary)


    summary = {
        "input_csv": str(input_path),
        "feature_space_config_path": str(feature_space_config_path),
        "feature_space_config_loaded": bool(feature_space_cfg),
        "feature_space_manifest_json": str(DEFAULT_STEP12_MANIFEST),
        "feature_space_manifest_loaded": bool(feature_manifest),
        "dictionary_csv": str(dictionary_path),
        "dataset_csv": str(dataset_path),
        "selected_feature_columns_json": str(selected_features_path),
        "n_rows_input": int(len(work)),
        "n_rows_dictionary_pool": int(len(dictionary_pool)),
        "n_rows_dictionary": int(len(dictionary)),
        "n_rows_dictionary_before_dedup": int(n_before_dedup),
        "n_rows_deduplicated": int(n_before_dedup - len(dictionary)),
        "dedup_parameter_columns": param_dedup_cols,
        "n_rows_dataset": int(len(dataset)),
        "events_column": events_col,
        "split": split_report,
        "dictionary_quality": quality_report,
        "efficiency_fit": {
            "polynomial_order_requested": int(poly_order),
            "models": fit_models,
            "relerr_columns_raw": relerr_cols_raw,
            "relerr_columns_fit": relerr_cols_fit,
        },
        "continuity_validation": {
            "enabled": False,
            "status": "SKIPPED",
            "messages": ["STEP 1.3 does not run continuity; use STEP 1.4."],
            "checks": {},
        },
        "selected_feature_columns_info": selected_feature_info,
        "tt_rate_passthrough": tt_passthrough_info,
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    log.info("Wrote dictionary: %s (%d rows)", dictionary_path, len(dictionary))
    log.info("Wrote holdout dataset: %s (%d rows)", dataset_path, len(dataset))
    log.info("Wrote selected features: %s (%d columns)", selected_features_path, len(selected_feature_columns))
    log.info("Wrote summary: %s", summary_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
