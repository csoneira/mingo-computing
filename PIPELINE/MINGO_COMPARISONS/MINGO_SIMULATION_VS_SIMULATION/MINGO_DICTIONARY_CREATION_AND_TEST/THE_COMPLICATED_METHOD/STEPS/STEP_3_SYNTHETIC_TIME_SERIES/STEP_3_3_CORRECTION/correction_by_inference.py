#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_SIMULATION/MINGO_DICTIONARY_CREATION_AND_TEST/STEPS/STEP_3_SYNTHETIC_TIME_SERIES/STEP_3_3_CORRECTION/correction_by_inference.py
Purpose: STEP 3.3 — Correction by inference on synthetic dataset.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_SIMULATION/MINGO_DICTIONARY_CREATION_AND_TEST/STEPS/STEP_3_SYNTHETIC_TIME_SERIES/STEP_3_3_CORRECTION/correction_by_inference.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

import argparse
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

# ── Paths ────────────────────────────────────────────────────────────────
STEP_DIR = Path(__file__).resolve().parent
SYNTHETIC_DIR = STEP_DIR.parent
PIPELINE_DIR = SYNTHETIC_DIR.parent
PROJECT_DIR = PIPELINE_DIR.parent
DEFAULT_CONFIG = (
    PIPELINE_DIR / "STEP_1_SETUP" / "STEP_1_1_COLLECT_DATA" / "INPUTS" / "config_step_1.1_method.json"
)
CONFIG_COLUMNS_PATH = (
    PIPELINE_DIR / "STEP_2_INFERENCE" / "STEP_2_1_ESTIMATE_PARAMS" / "INPUTS" / "config_step_2.1_columns.json"
)

DEFAULT_SYNTHETIC_DATASET = (
    SYNTHETIC_DIR / "STEP_3_2_SYNTHETIC_TIME_SERIES" / "OUTPUTS" / "FILES" / "synthetic_dataset.csv"
)
DEFAULT_STEP32_DIAGNOSTIC_CENTER = (
    SYNTHETIC_DIR / "STEP_3_2_SYNTHETIC_TIME_SERIES" / "OUTPUTS" / "FILES" / "diagnostic_center_series.csv"
)
DEFAULT_TIME_SERIES = (
    SYNTHETIC_DIR / "STEP_3_1_TIME_SERIES_CREATION" / "OUTPUTS" / "FILES" / "time_series.csv"
)
DEFAULT_COMPLETE_CURVE = (
    SYNTHETIC_DIR / "STEP_3_1_TIME_SERIES_CREATION" / "OUTPUTS" / "FILES" / "complete_curve_time_series.csv"
)
DEFAULT_DICTIONARY = (
    PIPELINE_DIR / "STEP_1_SETUP" / "STEP_1_4_ENSURE_CONTINUITY_DICTIONARY" / "OUTPUTS" / "FILES" / "dictionary.csv"
)
DEFAULT_DATASET_TEMPLATE = (
    PIPELINE_DIR / "STEP_1_SETUP" / "STEP_1_4_ENSURE_CONTINUITY_DICTIONARY" / "OUTPUTS" / "FILES" / "dataset.csv"
)
DEFAULT_STEP12_SELECTED_FEATURE_COLUMNS = (
    PIPELINE_DIR / "STEP_1_SETUP" / "STEP_1_4_ENSURE_CONTINUITY_DICTIONARY" / "OUTPUTS" / "FILES" / "selected_feature_columns.json"
)
DEFAULT_PARAMETER_SPACE_SPEC = (
    PIPELINE_DIR
    / "STEP_1_SETUP"
    / "STEP_1_1_COLLECT_DATA"
    / "OUTPUTS"
    / "FILES"
    / "parameter_space_columns.json"
)
DEFAULT_LUT = (
    PIPELINE_DIR / "STEP_2_INFERENCE" / "STEP_2_3_UNCERTAINTY" / "OUTPUTS" / "FILES" / "uncertainty_lut.csv"
)
DEFAULT_LUT_META = (
    PIPELINE_DIR / "STEP_2_INFERENCE" / "STEP_2_3_UNCERTAINTY" / "OUTPUTS" / "FILES" / "uncertainty_lut_meta.json"
)
DEFAULT_BUILD_SUMMARY = (
    PIPELINE_DIR / "STEP_1_SETUP" / "STEP_1_3_BUILD_DICTIONARY" / "OUTPUTS" / "FILES" / "build_summary.json"
)

FILES_DIR = STEP_DIR / "OUTPUTS" / "FILES"
PLOTS_DIR = STEP_DIR / "OUTPUTS" / "PLOTS"
FILES_DIR.mkdir(parents=True, exist_ok=True)
PLOTS_DIR.mkdir(parents=True, exist_ok=True)

_FIGURE_COUNTER = 0
FIGURE_STEP_PREFIX = "3_3"


def _save_figure(fig: plt.Figure, path: Path, **kwargs) -> None:
    """Save figure with a per-script sequential numeric prefix."""
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

logging.basicConfig(
    format="[%(levelname)s] STEP_3.3 — %(message)s", level=logging.INFO
)
log = logging.getLogger("STEP_3.3")

CANONICAL_FLUX_COLUMN = "flux_cm2_min"
CANONICAL_EFF_COLUMN = "eff_sim_1"

MODULES_DIR = PIPELINE_DIR / "MODULES"
if str(MODULES_DIR) not in sys.path:
    sys.path.insert(0, str(MODULES_DIR))
try:
    from efficiency_fit_utils import (  # noqa: E402
        append_polynomial_corrected_efficiency_columns,
        load_efficiency_fit_models,
    )
    from uncertainty_lut import (  # noqa: E402
        detect_uncertainty_lut_param_names,
        interpolate_uncertainty_columns,
        load_uncertainty_lut_table,
    )
except Exception as exc:
    log.error("Failed to import efficiency_fit_utils from %s: %s", MODULES_DIR, exc)
    raise

# Import estimation function from STEP 2 module.
INFERENCE_DIR = PIPELINE_DIR / "STEP_2_INFERENCE"
if str(INFERENCE_DIR) not in sys.path:
    sys.path.insert(0, str(INFERENCE_DIR))
try:
    from inference_runtime import (  # noqa: E402
        log_runtime_inverse_mapping_summary,
        parse_column_spec as _shared_parse_column_spec,
        require_selected_feature_columns_present as _shared_require_selected_feature_columns_present,
        resolve_estimation_parameter_columns as _shared_resolve_estimation_parameter_columns,
        resolve_runtime_distance_and_inverse_mapping,
    )
    from estimate_parameters import (  # noqa: E402
        PHYSICAL_TT_RATE_LABELS,
        _append_derived_physics_feature_columns,
        _append_derived_tt_global_rate_column,
        _auto_feature_columns as _shared_auto_feature_columns,
        _derived_feature_columns as _shared_derived_feature_columns,
        _normalize_derived_physics_features,
        resolve_physical_tt_rate_columns,
        estimate_from_dataframes,
        require_explicit_columns_present_in_both_frames,
    )
    from feature_columns_config import (  # noqa: E402
        parse_explicit_feature_columns,
        resolve_feature_columns_from_catalog,
        sync_feature_column_catalog,
    )
except Exception as exc:
    log.error("Failed to import estimate_parameters from %s: %s", INFERENCE_DIR, exc)
    raise


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

def _safe_float(value: object, default: float) -> float:
    """Convert value to float with fallback."""
    try:
        out = float(value)
    except (TypeError, ValueError):
        return float(default)
    if np.isfinite(out):
        return out
    return float(default)


def _safe_bool(value: object, default: bool) -> bool:
    """Convert common truthy/falsy representations to bool."""
    if isinstance(value, bool):
        return value
    if value is None:
        return bool(default)
    s = str(value).strip().lower()
    if s in {"1", "true", "yes", "y", "on"}:
        return True
    if s in {"0", "false", "no", "n", "off"}:
        return False
    return bool(default)


COMMON_FEATURE_SPACE_KEYS = (
    "feature_columns",
    "derived_features",
    "include_global_rate",
    "global_rate_col",
)


def _merge_common_feature_space_cfg(
    config: dict,
    cfg_21: dict | None = None,
) -> tuple[dict, dict]:
    """Merge top-level common feature-space config with STEP 2.1 overrides."""
    merged: dict = {}
    source_info: dict = {
        "common_keys": [],
        "step_2_1_override_keys": [],
        "has_common_feature_space": False,
    }
    common_cfg = config.get("common_feature_space", {}) if isinstance(config, dict) else {}
    if isinstance(common_cfg, dict):
        source_info["has_common_feature_space"] = True
        for key in COMMON_FEATURE_SPACE_KEYS:
            if key in common_cfg and common_cfg.get(key) is not None:
                merged[key] = common_cfg.get(key)
                source_info["common_keys"].append(key)
    cfg_21_local = cfg_21 if isinstance(cfg_21, dict) else {}
    for key in COMMON_FEATURE_SPACE_KEYS:
        if key in cfg_21_local and cfg_21_local.get(key) is not None:
            merged[key] = cfg_21_local.get(key)
            source_info["step_2_1_override_keys"].append(key)
    cfg_merged = dict(cfg_21_local)
    cfg_merged.update(merged)
    return cfg_merged, source_info


def _resolve_input_path(path_like: str | Path) -> Path:
    """Resolve path relative to pipeline when not absolute."""
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


def _load_step12_selected_feature_columns(path: Path) -> tuple[list[str], dict]:
    """Load selected feature-column artifact generated by STEP 1.2."""
    info: dict = {"path": str(path), "exists": bool(path.exists())}
    if not path.exists():
        return [], info
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        info["error"] = str(exc)
        return [], info
    raw_cols = payload.get("selected_feature_columns", [])
    if not isinstance(raw_cols, list):
        info["error"] = "selected_feature_columns_not_list"
        return [], info
    selected = [str(c).strip() for c in raw_cols if str(c).strip()]
    info["selected_count"] = int(len(selected))
    info["selection_strategy"] = payload.get("selection_strategy", None)
    return selected, info


def _resolve_selected_step12_feature_columns_strict(
    selected_feature_columns: list[str],
    *,
    dict_df: pd.DataFrame,
    data_df: pd.DataFrame,
) -> list[str]:
    return _shared_require_selected_feature_columns_present(
        selected_feature_columns,
        dict_df=dict_df,
        data_df=data_df,
        context_label="STEP 3.3",
        right_label="dataset",
    )


def _load_step13_efficiency_fit(path: Path) -> tuple[dict[int, dict[str, object]], dict]:
    """Load STEP 1.3 empirical-efficiency polynomial fit metadata."""
    fit_models, fit_status, payload = load_efficiency_fit_models(path)
    efficiency_fit = payload.get("efficiency_fit", {}) if isinstance(payload, dict) else {}
    info: dict[str, object] = {
        "path": str(path),
        "exists": bool(path.exists()),
        "status": fit_status,
        "planes_loaded": sorted(int(plane) for plane in fit_models.keys()),
        "polynomial_order_requested": (
            efficiency_fit.get("polynomial_order_requested")
            if isinstance(efficiency_fit, dict)
            else None
        ),
    }
    return fit_models, info


def _append_step13_polynomial_efficiency_products(
    df: pd.DataFrame,
    *,
    build_summary_path: Path,
) -> dict[str, object]:
    """Append STEP 1.3 polynomial-corrected efficiency columns for TT diagnostics."""
    fit_models, load_info = _load_step13_efficiency_fit(build_summary_path)
    append_info = append_polynomial_corrected_efficiency_columns(df, fit_models)
    info = dict(load_info)
    info["application"] = append_info
    if append_info.get("status") == "ok":
        log.info(
            "Applied STEP 1.3 polynomial efficiency correction from %s: planes=%s, products=%s",
            build_summary_path,
            append_info.get("planes_applied", []),
            append_info.get("efficiency_product_columns_created", []),
        )
    else:
        log.warning(
            "STEP 1.3 polynomial efficiency correction unavailable for STEP 3.3 TT plot "
            "(summary=%s, load_status=%s, apply_status=%s).",
            build_summary_path,
            load_info.get("status"),
            append_info.get("status"),
        )
    return info


def _choose_eff_column(df: pd.DataFrame, preferred: str) -> str:
    """Select an efficiency column from dataframe with fallback candidates."""
    if preferred in df.columns:
        return preferred
    for candidate in (
        "eff_sim_1", "eff_sim_2", "eff_sim_3", "eff_sim_4",
        "eff_empirical_1", "eff_empirical_2", "eff_empirical_3", "eff_empirical_4",
    ):
        if candidate in df.columns:
            return candidate
    raise KeyError("No efficiency column found in dataframe.")


def _choose_flux_column(df: pd.DataFrame, preferred: str = CANONICAL_FLUX_COLUMN) -> str | None:
    """Select a flux-like parameter column when available."""
    candidates: list[str] = []
    if str(preferred).strip():
        candidates.append(str(preferred).strip())
    candidates.extend([c for c in DEFAULT_PARAMETER_SPACE_PRIORITY if "flux" in str(c).lower()])
    candidates.extend(sorted(c for c in df.columns if "flux" in str(c).lower()))

    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen or candidate not in df.columns:
            continue
        seen.add(candidate)
        values = pd.to_numeric(df[candidate], errors="coerce")
        if values.notna().any():
            return candidate
    return None


def _load_parameter_space_spec(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("Could not load parameter-space spec %s: %s", path, exc)
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_parameter_space_columns(path: Path) -> list[str]:
    payload = _load_parameter_space_spec(path)
    if not payload:
        return []
    candidates: list[object] = [
        payload.get("parameter_space_columns_downstream_preferred"),
        payload.get("selected_parameter_space_columns_downstream_preferred"),
        payload.get("selected_parameter_space_columns"),
        payload.get("parameter_space_columns"),
    ]
    out: list[str] = []
    seen: set[str] = set()
    for raw in candidates:
        if not isinstance(raw, list):
            continue
        for col in raw:
            if not isinstance(col, str):
                continue
            text = col.strip()
            if not text or text in seen:
                continue
            out.append(text)
            seen.add(text)
        if out:
            break
    return out


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


DEFAULT_PARAMETER_SPACE_PRIORITY = [
    "flux_cm2_min",
    "cos_n",
    "eff_sim_1",
    "eff_sim_2",
    "eff_sim_3",
    "eff_sim_4",
    "eff_empirical_1",
    "eff_empirical_2",
    "eff_empirical_3",
    "eff_empirical_4",
]


def _is_parameter_space_column(name: str) -> bool:
    col = str(name).strip()
    if not col:
        return False
    if col in {"flux_cm2_min", "cos_n"}:
        return True
    if col.startswith("eff_sim_"):
        return True
    if col.startswith("eff_empirical_"):
        return True
    return False


def _parse_column_spec(value: object) -> list[str]:
    """Parse list-like config values accepting arrays or comma-separated text."""
    return _shared_parse_column_spec(value)


def _resolve_parameter_space_columns_from_cfg(
    *,
    merged_df: pd.DataFrame,
    dictionary_df: pd.DataFrame,
    configured_columns: object = None,
    default_columns: list[str] | None = None,
) -> list[str]:
    """Resolve parameter-space columns with available weighted/corrected pairs."""

    def _has_weighted_and_corrected(col: str) -> bool:
        if col not in merged_df.columns:
            return False
        return (f"corrected_{col}" in merged_df.columns) or (f"est_{col}" in merged_df.columns)

    common_dict = set(dictionary_df.columns)
    requested = _parse_column_spec(configured_columns)
    if not requested and isinstance(default_columns, list):
        requested = [str(c).strip() for c in default_columns if str(c).strip()]

    if requested:
        resolved: list[str] = []
        missing: list[str] = []
        for col in requested:
            if col in common_dict and _has_weighted_and_corrected(col):
                if col not in resolved:
                    resolved.append(col)
            else:
                missing.append(col)
        if missing:
            log.warning(
                "Ignoring STEP 3.3 parameter_space_columns without dictionary/weighted/corrected support: %s",
                missing,
            )
        if resolved:
            return resolved
        raise KeyError("No configured STEP 3.3 parameter_space_columns are available.")

    resolved_auto: list[str] = []
    for col in DEFAULT_PARAMETER_SPACE_PRIORITY:
        if col in common_dict and _has_weighted_and_corrected(col) and col not in resolved_auto:
            resolved_auto.append(col)

    for col in sorted(common_dict):
        if col in resolved_auto:
            continue
        if _is_parameter_space_column(col) and _has_weighted_and_corrected(col):
            resolved_auto.append(col)

    if resolved_auto:
        return resolved_auto

    # Fallback: any estimated parameter with a base counterpart present in dictionary.
    for col in merged_df.columns:
        if not str(col).startswith("est_"):
            continue
        base = str(col)[len("est_"):]
        if base in common_dict and base in merged_df.columns:
            resolved_auto.append(base)
    if resolved_auto:
        return sorted(set(resolved_auto))

    raise KeyError("Could not resolve STEP 3.3 parameter-space columns.")


def _resolve_estimation_parameter_columns(
    *,
    dictionary_df: pd.DataFrame,
    configured_columns: object = None,
    default_columns: list[str] | None = None,
) -> list[str]:
    return _shared_resolve_estimation_parameter_columns(
        dictionary_df=dictionary_df,
        configured_columns=configured_columns,
        default_columns=default_columns,
        default_priority=DEFAULT_PARAMETER_SPACE_PRIORITY,
        parameter_predicate=_is_parameter_space_column,
        logger=log,
    )


def _find_true_parameter_column(df: pd.DataFrame, pname: str) -> str | None:
    true_col = f"true_{pname}"
    if true_col in df.columns:
        return true_col
    if pname in df.columns:
        return pname
    return None


def _find_estimated_parameter_column(df: pd.DataFrame, pname: str) -> str | None:
    for candidate in (f"corrected_{pname}", f"est_{pname}"):
        if candidate in df.columns:
            return candidate
    return None


def _is_efficiency_parameter_column(name: str) -> bool:
    text = str(name).strip().lower()
    return text.startswith("eff_") or "_eff_" in text or text.endswith("_eff") or text.startswith("eff")


def _series_median_or_none(values: object) -> float | None:
    if values is None:
        return None
    series = pd.to_numeric(values, errors="coerce")
    if isinstance(series, pd.Series):
        if not series.notna().any():
            return None
        return float(series.median())
    arr = np.asarray(series, dtype=float)
    if not np.isfinite(arr).any():
        return None
    return float(np.nanmedian(arr))


def _append_parameter_error_metrics(
    df: pd.DataFrame,
    *,
    parameter_space_cols: list[str],
) -> dict[str, dict[str, object]]:
    """Append per-parameter error columns and return compact diagnostics."""
    diagnostics: dict[str, dict[str, object]] = {}
    for pname in parameter_space_cols:
        true_col = _find_true_parameter_column(df, pname)
        est_col = _find_estimated_parameter_column(df, pname)
        if true_col is None or est_col is None:
            continue

        true_vals = pd.to_numeric(df.get(true_col), errors="coerce")
        est_vals = pd.to_numeric(df.get(est_col), errors="coerce")
        err_vals = est_vals - true_vals
        rel_vals = err_vals / true_vals.replace({0.0: np.nan}) * 100.0
        abs_rel_vals = rel_vals.abs()

        df[f"error_{pname}"] = err_vals
        df[f"relerr_{pname}_pct"] = rel_vals
        df[f"abs_relerr_{pname}_pct"] = abs_rel_vals

        unc_pct_col = f"unc_{pname}_pct" if f"unc_{pname}_pct" in df.columns else None
        unc_abs_col = f"unc_{pname}_abs" if f"unc_{pname}_abs" in df.columns else None
        diagnostics[pname] = {
            "true_column": true_col,
            "estimated_column": est_col,
            "uncertainty_pct_column": unc_pct_col,
            "uncertainty_abs_column": unc_abs_col,
            "n_finite_estimates": int(est_vals.notna().sum()),
            "median_abs_relerr_pct": _series_median_or_none(abs_rel_vals),
            "median_unc_pct": _series_median_or_none(df.get(unc_pct_col) if unc_pct_col else None),
        }
    return diagnostics


def _build_parameter_diagnostic_panels(
    df: pd.DataFrame,
    *,
    parameter_space_cols: list[str],
) -> list[tuple[str, np.ndarray, np.ndarray, np.ndarray | None]]:
    panels: list[tuple[str, np.ndarray, np.ndarray, np.ndarray | None]] = []
    for pname in parameter_space_cols:
        true_col = f"true_{pname}" if f"true_{pname}" in df.columns else (pname if pname in df.columns else None)
        est_col = (
            f"corrected_{pname}"
            if f"corrected_{pname}" in df.columns
            else f"est_{pname}"
            if f"est_{pname}" in df.columns
            else None
        )
        if true_col is None or est_col is None:
            continue
        true_vals = pd.to_numeric(df.get(true_col), errors="coerce").to_numpy(dtype=float)
        est_vals = pd.to_numeric(df.get(est_col), errors="coerce").to_numpy(dtype=float)
        if not (np.isfinite(true_vals).any() and np.isfinite(est_vals).any()):
            continue
        unc_col = f"unc_{pname}_abs"
        unc_vals = (
            pd.to_numeric(df.get(unc_col), errors="coerce").to_numpy(dtype=float)
            if unc_col in df.columns
            else None
        )
        panels.append((pname, true_vals, est_vals, unc_vals))
    return panels


def _resolve_inference_feature_columns(
    *,
    feature_cfg: object,
    dict_df: pd.DataFrame,
    data_df: pd.DataFrame,
    include_global_rate: bool,
    global_rate_col: str,
    step12_selected_path: Path | None = None,
    derived_feature_cfg: object = None,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str], str]:
    """Resolve feature columns for STEP 3.3 inference using STEP 2.1 criteria."""
    auto_feature_cols = sorted(
        set(_shared_auto_feature_columns(dict_df, include_global_rate, global_rate_col))
        & set(_shared_auto_feature_columns(data_df, include_global_rate, global_rate_col))
    )
    catalog = sync_feature_column_catalog(
        catalog_path=CONFIG_COLUMNS_PATH,
        dict_df=dict_df,
        default_enabled_columns=auto_feature_cols,
    )
    derived_cfg_raw = (
        derived_feature_cfg
        if isinstance(derived_feature_cfg, dict)
        else {}
    )
    categories = catalog.get("categories", {})
    if not isinstance(categories, dict):
        categories = {}
    trigger_cfg = categories.get("trigger_type", {})
    if not isinstance(trigger_cfg, dict):
        trigger_cfg = {}
    rate_hist_cfg = categories.get("rate_histogram", {})
    if not isinstance(rate_hist_cfg, dict):
        rate_hist_cfg = {}

    derived_tt_prefix = str(
        derived_cfg_raw.get("prefix", catalog.get("prefix", "last"))
    ).strip() or "last"
    derived_trigger_types = parse_explicit_feature_columns(
        derived_cfg_raw.get("trigger_types", trigger_cfg.get("trigger_types", []))
    )
    derived_include_to_tt = _safe_bool(
        derived_cfg_raw.get(
            "include_to_tt_rate_hz",
            derived_cfg_raw.get(
                "include_to_prefix_rates",
                catalog.get("*_to_*_tt_*_rate_hz", False),
            ),
        ),
        bool(catalog.get("*_to_*_tt_*_rate_hz", False)),
    )
    derived_include_trigger_rates = _safe_bool(
        derived_cfg_raw.get("include_trigger_type_rates", False),
        False,
    )
    derived_include_hist = _safe_bool(
        derived_cfg_raw.get(
            "include_rate_histogram",
            rate_hist_cfg.get("enabled", catalog.get("*_*_rate_hz", False)),
        ),
        bool(rate_hist_cfg.get("enabled", catalog.get("*_*_rate_hz", False))),
    )
    derived_physics_features = _normalize_derived_physics_features(
        derived_cfg_raw.get("physics_features", [])
    )

    def _materialize_derived_space(
        dict_in: pd.DataFrame,
        data_in: pd.DataFrame,
    ) -> tuple[pd.DataFrame, pd.DataFrame, str | None, list[str], list[str]]:
        (
            dict_derived,
            data_derived,
            derived_rate_col,
            derived_rate_sources,
        ) = _append_derived_tt_global_rate_column(
            dict_df=dict_in,
            data_df=data_in,
            prefix_selector=derived_tt_prefix,
            trigger_type_allowlist=derived_trigger_types,
            include_to_tt_rate_hz=bool(derived_include_to_tt),
        )
        if (
            derived_rate_col is None
            and include_global_rate
            and global_rate_col in dict_in.columns
            and global_rate_col in data_in.columns
        ):
            derived_rate_col = str(global_rate_col)
        if derived_rate_col is None:
            return dict_derived, data_derived, None, [], []
        (
            dict_derived,
            data_derived,
            derived_physics_cols,
        ) = _append_derived_physics_feature_columns(
            dict_df=dict_derived,
            data_df=data_derived,
            rate_column=derived_rate_col,
            physics_features=derived_physics_features,
        )
        return (
            dict_derived,
            data_derived,
            str(derived_rate_col),
            [str(c) for c in derived_rate_sources],
            [str(c) for c in derived_physics_cols],
        )

    if isinstance(feature_cfg, str):
        mode = feature_cfg.strip().lower()
        selected_feature_modes = {
            "step12_selected",
            "step_1_2_selected",
            "selected_from_step12",
            "selected_from_step_1_2",
        }
        if mode in selected_feature_modes:
            selected_path = (
                Path(step12_selected_path).expanduser()
                if step12_selected_path is not None
                else DEFAULT_STEP12_SELECTED_FEATURE_COLUMNS
            )
            selected_from_step12, selected_info = _load_step12_selected_feature_columns(selected_path)
            dict_selected, data_selected, _, _, _ = _materialize_derived_space(dict_df, data_df)
            try:
                selected = _resolve_selected_step12_feature_columns_strict(
                    selected_from_step12,
                    dict_df=dict_selected,
                    data_df=data_selected,
                )
            except ValueError as exc:
                if selected_info.get("error"):
                    raise ValueError(
                        f"STEP 1.2 selected features at {selected_path} are invalid "
                        f"({selected_info.get('error')}): {exc}"
                    ) from exc
                raise
            log.info(
                "Using STEP 1.2 selected features (%d) from %s.",
                len(selected),
                selected_path,
            )
            return dict_selected, data_selected, selected, "step12_selected"
        if mode == "auto":
            return dict_df, data_df, auto_feature_cols, "auto"
        if mode == "derived":
            (
                dict_derived,
                data_derived,
                derived_rate_col,
                derived_rate_sources,
                derived_physics_cols,
            ) = _materialize_derived_space(dict_df, data_df)
            if derived_rate_col is None:
                raise ValueError(
                    "No derived feature global-rate source available. "
                    "TT trigger-type sum could not be built and fallback global-rate column is missing."
                )
            feat_dict = _shared_derived_feature_columns(
                dict_derived,
                rate_column=derived_rate_col,
                trigger_type_rate_columns=(
                    derived_rate_sources
                    if bool(derived_include_trigger_rates)
                    else None
                ),
                include_rate_histogram=bool(derived_include_hist),
                physics_feature_columns=derived_physics_cols,
            )
            feat_data = _shared_derived_feature_columns(
                data_derived,
                rate_column=derived_rate_col,
                trigger_type_rate_columns=(
                    derived_rate_sources
                    if bool(derived_include_trigger_rates)
                    else None
                ),
                include_rate_histogram=bool(derived_include_hist),
                physics_feature_columns=derived_physics_cols,
            )
            selected = sorted(set(feat_dict) & set(feat_data))
            if not selected:
                raise ValueError(
                    "No derived feature columns found in dictionary/dataset intersection. "
                    "Expected eff_empirical_1..4 and at least one global-rate feature."
                )
            log.info(
                "Derived features: prefix=%s trigger_types=%s include_hist=%s "
                "include_trigger_rates=%s physics=%s rate_feature=%s rate_sources=%s",
                derived_tt_prefix,
                derived_trigger_types,
                bool(derived_include_hist),
                bool(derived_include_trigger_rates),
                derived_physics_features,
                derived_rate_col,
                derived_rate_sources,
            )
            return dict_derived, data_derived, selected, "derived"
        if mode in {"config_columns", "catalog", "config_columns_json"}:
            selected, info = resolve_feature_columns_from_catalog(
                catalog=catalog,
                available_columns=sorted(set(dict_df.columns) & set(data_df.columns)),
            )
            if info.get("invalid_include_patterns"):
                log.warning(
                    "Ignoring invalid include pattern(s) in %s: %s",
                    CONFIG_COLUMNS_PATH,
                    info.get("invalid_include_patterns"),
                )
            if info.get("invalid_exclude_patterns"):
                log.warning(
                    "Ignoring invalid exclude pattern(s) in %s: %s",
                    CONFIG_COLUMNS_PATH,
                    info.get("invalid_exclude_patterns"),
                )
            if selected:
                return dict_df, data_df, selected, "config_columns"
            raise ValueError(
                "No features selected by config_columns catalog. "
                "Refusing to fall back to auto, because that would silently change the STEP 3.3 feature space."
            )

    requested = parse_explicit_feature_columns(feature_cfg)
    selected = require_explicit_columns_present_in_both_frames(
        requested,
        left_columns=dict_df.columns,
        right_columns=data_df.columns,
        left_label="dictionary",
        right_label="dataset",
        context_label="STEP 3.3",
    )
    return dict_df, data_df, selected, "explicit"


def _compute_density_center_series(
    *,
    config: dict,
    time_df: pd.DataFrame,
    flux_col: str,
    eff_pref: str,
    dictionary_path: Path,
    dataset_template_path: Path,
) -> tuple[np.ndarray | None, np.ndarray | None, str | None]:
    """Load STEP 3.2 diagnostic center series (no recomputation in STEP 3.3)."""
    _ = dictionary_path
    _ = dataset_template_path
    if time_df.empty:
        return None, None, None

    cfg_32 = config.get("step_3_2", {}) if isinstance(config, dict) else {}
    cfg_33 = config.get("step_3_3", {}) if isinstance(config, dict) else {}
    center_csv_cfg = (
        cfg_33.get("step32_diagnostic_center_csv", None)
        if isinstance(cfg_33, dict) else None
    )
    if center_csv_cfg in (None, "", "null", "None"):
        center_csv_cfg = (
            cfg_32.get("diagnostic_center_series_csv", None)
            if isinstance(cfg_32, dict) else None
        )
    center_path = _resolve_input_path(center_csv_cfg or DEFAULT_STEP32_DIAGNOSTIC_CENTER)
    if not center_path.exists():
        log.warning(
            "STEP 3.2 diagnostic center CSV not found: %s. "
            "STEP 3.3 overlay will omit the center curve.",
            center_path,
        )
        return None, None, None

    try:
        center_df = pd.read_csv(center_path, low_memory=False)
    except Exception as exc:
        log.warning("Could not read STEP 3.2 diagnostic center CSV %s: %s", center_path, exc)
        return None, None, None
    if center_df.empty:
        log.warning("STEP 3.2 diagnostic center CSV is empty: %s", center_path)
        return None, None, None

    flux_center_col = None
    for c in ("center_flux_cm2_min", "diagnostic_center_flux", "center_flux", flux_col):
        if c in center_df.columns:
            flux_center_col = c
            break
    if flux_center_col is None:
        log.warning("STEP 3.2 center CSV has no flux center column: %s", center_path)
        return None, None, None

    eff_col_time = eff_pref
    if "eff_column_used" in center_df.columns:
        eff_candidates = center_df["eff_column_used"].dropna().astype(str)
        if not eff_candidates.empty:
            eff_col_time = str(eff_candidates.iloc[0]).strip() or eff_pref
    else:
        try:
            eff_col_time = _choose_eff_column(time_df, eff_pref)
        except KeyError:
            eff_col_time = eff_pref

    eff_center_col = None
    for c in ("center_eff", "diagnostic_center_eff", eff_col_time, eff_pref):
        if c in center_df.columns:
            eff_center_col = c
            break
    if eff_center_col is None:
        log.warning("STEP 3.2 center CSV has no efficiency center column: %s", center_path)
        return None, None, eff_col_time

    n_rows = len(time_df)
    center_flux = np.full(n_rows, np.nan, dtype=float)
    center_eff = np.full(n_rows, np.nan, dtype=float)
    aligned_method = None

    if "file_index" in center_df.columns and "file_index" in time_df.columns:
        left = pd.DataFrame({
            "_row_idx": np.arange(n_rows, dtype=int),
            "file_index": pd.to_numeric(time_df["file_index"], errors="coerce"),
        })
        right = pd.DataFrame({
            "file_index": pd.to_numeric(center_df["file_index"], errors="coerce"),
            "_center_flux": pd.to_numeric(center_df[flux_center_col], errors="coerce"),
            "_center_eff": pd.to_numeric(center_df[eff_center_col], errors="coerce"),
        })
        aligned = left.merge(right, on="file_index", how="left", sort=False)
        center_flux = aligned["_center_flux"].to_numpy(dtype=float)
        center_eff = aligned["_center_eff"].to_numpy(dtype=float)
        if np.isfinite(center_flux).any() and np.isfinite(center_eff).any():
            aligned_method = "file_index"

    if aligned_method is None and "elapsed_hours" in center_df.columns and "elapsed_hours" in time_df.columns:
        left = pd.DataFrame({
            "_row_idx": np.arange(n_rows, dtype=int),
            "elapsed_hours_key": np.round(pd.to_numeric(time_df["elapsed_hours"], errors="coerce"), 10),
        })
        right = pd.DataFrame({
            "elapsed_hours_key": np.round(pd.to_numeric(center_df["elapsed_hours"], errors="coerce"), 10),
            "_center_flux": pd.to_numeric(center_df[flux_center_col], errors="coerce"),
            "_center_eff": pd.to_numeric(center_df[eff_center_col], errors="coerce"),
        })
        aligned = left.merge(right, on="elapsed_hours_key", how="left", sort=False)
        center_flux = aligned["_center_flux"].to_numpy(dtype=float)
        center_eff = aligned["_center_eff"].to_numpy(dtype=float)
        if np.isfinite(center_flux).any() and np.isfinite(center_eff).any():
            aligned_method = "elapsed_hours"

    if aligned_method is None:
        src_flux = pd.to_numeric(center_df[flux_center_col], errors="coerce").to_numpy(dtype=float)
        src_eff = pd.to_numeric(center_df[eff_center_col], errors="coerce").to_numpy(dtype=float)
        if len(src_flux) == n_rows:
            center_flux = src_flux
            center_eff = src_eff
            aligned_method = "row_order"
        else:
            take = min(n_rows, len(src_flux))
            center_flux[:take] = src_flux[:take]
            center_eff[:take] = src_eff[:take]
            aligned_method = "row_order_trim_pad"
            log.warning(
                "STEP 3.2 center-length mismatch (center=%d, time=%d). "
                "Applied positional trim/pad for first %d rows.",
                len(src_flux),
                n_rows,
                take,
            )

    finite_pairs = np.isfinite(center_flux) & np.isfinite(center_eff)
    if not np.any(finite_pairs):
        log.warning(
            "STEP 3.2 center CSV loaded but produced no finite aligned rows: %s",
            center_path,
        )
        return None, None, eff_col_time
    log.info(
        "Using STEP 3.2 center series from %s (alignment=%s, finite_pairs=%d/%d).",
        center_path,
        aligned_method,
        int(np.sum(finite_pairs)),
        int(n_rows),
    )
    return center_flux, center_eff, eff_col_time


def _time_axis(df: pd.DataFrame) -> tuple[np.ndarray, str]:
    """Return numeric time axis values and axis label."""
    if "elapsed_hours" in df.columns:
        x = pd.to_numeric(df["elapsed_hours"], errors="coerce").to_numpy(dtype=float)
        return x, "Elapsed time [hours]"
    if "file_index" in df.columns:
        x = pd.to_numeric(df["file_index"], errors="coerce").to_numpy(dtype=float)
        return x, "File index"
    return np.arange(len(df), dtype=float), "Index"


def _apply_mean_striped_background(ax: plt.Axes, y_vals: np.ndarray) -> None:
    """Apply stripes at 1%-of-mean increments, uniformly across the y-axis."""
    y_min, y_max = ax.get_ylim()
    if not (np.isfinite(y_min) and np.isfinite(y_max)):
        return
    span = y_max - y_min
    if span <= 0.0:
        return

    y_arr = np.asarray(y_vals, dtype=float)
    valid = np.isfinite(y_arr)
    if not np.any(valid):
        return
    mean_val = float(np.mean(y_arr[valid]))

    band = abs(mean_val) * 0.01
    if not np.isfinite(band) or band <= 0.0:
        band = span * 0.01
    if band <= 0.0:
        return

    ax.set_facecolor("#FFFFFF")
    idx = int(np.floor((y_min - mean_val) / band))
    y0 = mean_val + idx * band
    while y0 < y_max:
        y1 = y0 + band
        lo = max(y0, y_min)
        hi = min(y1, y_max)
        color = "#FFFFFF" if (idx % 2 == 0) else "#D8DDE4"
        if hi > lo:
            ax.axhspan(lo, hi, facecolor=color, alpha=1.0, linewidth=0.0, zorder=0)
        y0 = y1
        idx += 1
    ax.set_ylim(y_min, y_max)


def _plot_series_panel(
    ax: plt.Axes,
    x: np.ndarray,
    true_vals: np.ndarray,
    est_vals: np.ndarray,
    unc_abs: np.ndarray | None,
    ylabel: str,
    title: str,
) -> None:
    """Plot one time-series comparison panel with optional uncertainty band."""
    m = np.isfinite(x) & np.isfinite(true_vals) & np.isfinite(est_vals)
    if not np.any(m):
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        ax.grid(True, alpha=0.25)
        return

    xo = x[m]
    yt = true_vals[m]
    ye = est_vals[m]
    order = np.argsort(xo)
    xo = xo[order]
    yt = yt[order]
    ye = ye[order]

    if unc_abs is not None and len(unc_abs) == len(x):
        yu = np.asarray(unc_abs, dtype=float)[m][order]
        yu = np.where(np.isfinite(yu), np.abs(yu), np.nan)
        valid_band = np.isfinite(yu)
        if np.any(valid_band):
            ax.fill_between(
                xo[valid_band],
                ye[valid_band] - yu[valid_band],
                ye[valid_band] + yu[valid_band],
                color="#FF7F0E",
                alpha=0.20,
                linewidth=0.0,
                label="Estimated ± uncertainty",
            )

    ax.scatter(xo, yt, s=18, facecolors="white", edgecolors="#1F77B4", linewidths=0.8, label="Simulated (true)")
    ax.scatter(xo, ye, s=18, color="#D62728", alpha=0.9, linewidths=0.0, label="Estimated")
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    _apply_mean_striped_background(ax, np.concatenate([yt, ye]))
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best", fontsize=8)


def _plot_diag_panel(
    ax: plt.Axes,
    true_vals: np.ndarray,
    est_vals: np.ndarray,
    unc_abs: np.ndarray | None,
    xlabel: str,
    ylabel: str,
    title: str,
) -> None:
    """Plot true-vs-estimated diagonal panel with optional vertical uncertainty."""
    m = np.isfinite(true_vals) & np.isfinite(est_vals)
    if not np.any(m):
        ax.set_title(title)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.grid(True, alpha=0.25)
        return

    xt = true_vals[m]
    ye = est_vals[m]
    if unc_abs is not None and len(unc_abs) == len(true_vals):
        yu = np.asarray(unc_abs, dtype=float)[m]
        yu = np.where(np.isfinite(yu), np.abs(yu), np.nan)
        valid_yu = np.isfinite(yu)
        if np.any(valid_yu):
            ax.errorbar(
                xt[valid_yu],
                ye[valid_yu],
                yerr=yu[valid_yu],
                fmt="none",
                ecolor="#D62728",
                alpha=0.20,
                elinewidth=0.8,
                capsize=0,
                zorder=1,
            )

    ax.scatter(xt, ye, s=22, color="#D62728", alpha=0.85, linewidths=0.0, zorder=2)
    lo = float(np.nanmin(np.concatenate([xt, ye])))
    hi = float(np.nanmax(np.concatenate([xt, ye])))
    if not np.isfinite(lo) or not np.isfinite(hi):
        lo, hi = 0.0, 1.0
    if hi <= lo:
        pad = max(abs(lo) * 0.05, 1e-6)
    else:
        pad = 0.03 * (hi - lo)
    ax.plot([lo - pad, hi + pad], [lo - pad, hi + pad], "k--", linewidth=1.0)
    ax.set_xlim(lo - pad, hi + pad)
    ax.set_ylim(lo - pad, hi + pad)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_aspect("equal", adjustable="box")
    _apply_mean_striped_background(ax, np.concatenate([xt, ye]))
    ax.grid(True, alpha=0.25)


def _plot_step32_style_overlay(
    *,
    complete_df: pd.DataFrame | None,
    time_df: pd.DataFrame,
    merged_df: pd.DataFrame,
    flux_col: str,
    eff_col_time: str,
    est_flux_col: str,
    est_eff_col: str,
    flux_unc_abs_col: str | None,
    eff_unc_abs_col: str | None,
    center_flux: np.ndarray | None,
    center_eff: np.ndarray | None,
    path: Path,
) -> None:
    """Plot complete+discretized+STEP3.2-center+estimated without global rate."""
    fig, axes = plt.subplots(
        3,
        1,
        figsize=(11.2, 9.1),
        sharex=True,
        gridspec_kw={"height_ratios": [0.9, 1.0, 1.0]},
    )

    # Discretized STEP 3.1 trajectory
    x_disc, x_label = _time_axis(time_df)
    y_flux_disc = pd.to_numeric(time_df.get(flux_col), errors="coerce").to_numpy(dtype=float)
    y_eff_disc = pd.to_numeric(time_df.get(eff_col_time), errors="coerce").to_numpy(dtype=float)
    flux_stripe_vals = [y_flux_disc]
    eff_stripe_vals = [y_eff_disc]

    # Complete trajectory
    if complete_df is not None and not complete_df.empty:
        x_comp, _ = _time_axis(complete_df)
        y_flux_comp = pd.to_numeric(complete_df.get(flux_col), errors="coerce").to_numpy(dtype=float)
        y_eff_comp = pd.to_numeric(complete_df.get(eff_col_time), errors="coerce").to_numpy(dtype=float)
        flux_stripe_vals.append(y_flux_comp)
        eff_stripe_vals.append(y_eff_comp)
        m0c = np.isfinite(x_comp) & np.isfinite(y_flux_comp)
        m1c = np.isfinite(x_comp) & np.isfinite(y_eff_comp)
        if np.any(m0c):
            axes[1].scatter(
                x_comp[m0c], y_flux_comp[m0c], s=7, color="#1F77B4", alpha=0.55, linewidths=0.0, label="Complete"
            )
        if np.any(m1c):
            axes[2].scatter(
                x_comp[m1c], y_eff_comp[m1c], s=7, color="#FF7F0E", alpha=0.55, linewidths=0.0, label="Complete"
            )

    m0d = np.isfinite(x_disc) & np.isfinite(y_flux_disc)
    m1d = np.isfinite(x_disc) & np.isfinite(y_eff_disc)
    if np.any(m0d):
        axes[1].scatter(
            x_disc[m0d],
            y_flux_disc[m0d],
            s=18,
            facecolors="white",
            edgecolors="#1F77B4",
            linewidths=0.8,
            label="Discretized",
        )
    if np.any(m1d):
        axes[2].scatter(
            x_disc[m1d],
            y_eff_disc[m1d],
            s=18,
            facecolors="white",
            edgecolors="#FF7F0E",
            linewidths=0.8,
            label="Discretized",
        )

    # STEP 3.2 reference center (loaded from STEP 3.2 outputs, no recomputation here).
    if center_flux is not None and len(center_flux) == len(x_disc):
        c_flux = np.asarray(center_flux, dtype=float)
        flux_stripe_vals.append(c_flux)
        mc = np.isfinite(x_disc) & np.isfinite(c_flux)
        if np.any(mc):
            axes[1].plot(
                x_disc[mc], c_flux[mc],
                color="#17BECF", linewidth=1.0, linestyle="-.", marker="s", markersize=2.8,
                markerfacecolor="#17BECF", markeredgewidth=0.0, alpha=0.9,
                label="STEP 3.2 reference center",
            )
    if center_eff is not None and len(center_eff) == len(x_disc):
        c_eff = np.asarray(center_eff, dtype=float)
        eff_stripe_vals.append(c_eff)
        mc = np.isfinite(x_disc) & np.isfinite(c_eff)
        if np.any(mc):
            axes[2].plot(
                x_disc[mc], c_eff[mc],
                color="#BCBD22", linewidth=1.0, linestyle="-.", marker="s", markersize=2.8,
                markerfacecolor="#BCBD22", markeredgewidth=0.0, alpha=0.9,
                label="STEP 3.2 reference center",
            )

    # Estimated series (+ uncertainty)
    x_est, _ = _time_axis(merged_df)
    y_flux_est = pd.to_numeric(merged_df.get(est_flux_col), errors="coerce").to_numpy(dtype=float)
    y_eff_est = pd.to_numeric(merged_df.get(est_eff_col), errors="coerce").to_numpy(dtype=float)
    flux_stripe_vals.append(y_flux_est)
    eff_stripe_vals.append(y_eff_est)
    u_flux = (
        pd.to_numeric(merged_df.get(flux_unc_abs_col), errors="coerce").to_numpy(dtype=float)
        if flux_unc_abs_col and flux_unc_abs_col in merged_df.columns
        else None
    )
    u_eff = (
        pd.to_numeric(merged_df.get(eff_unc_abs_col), errors="coerce").to_numpy(dtype=float)
        if eff_unc_abs_col and eff_unc_abs_col in merged_df.columns
        else None
    )

    m0e = np.isfinite(x_est) & np.isfinite(y_flux_est)
    if np.any(m0e):
        order = np.argsort(x_est[m0e])
        xe = x_est[m0e][order]
        ye = y_flux_est[m0e][order]
        axes[1].plot(
            xe, ye,
            color="#D62728", linewidth=1.0, linestyle="-", marker="o", markersize=3.0,
            markerfacecolor="#D62728", markeredgewidth=0.0, alpha=0.9,
            label="Estimated",
        )
        if u_flux is not None and len(u_flux) == len(x_est):
            ue = np.abs(u_flux[m0e][order])
            valid_u = np.isfinite(ue)
            if np.any(valid_u):
                axes[1].fill_between(
                    xe[valid_u], ye[valid_u] - ue[valid_u], ye[valid_u] + ue[valid_u],
                    color="#D62728", alpha=0.16, linewidth=0.0, label="Estimated ± uncertainty",
                )

    m1e = np.isfinite(x_est) & np.isfinite(y_eff_est)
    if np.any(m1e):
        order = np.argsort(x_est[m1e])
        xe = x_est[m1e][order]
        ye = y_eff_est[m1e][order]
        axes[2].plot(
            xe, ye,
            color="#8C564B", linewidth=1.0, linestyle="-", marker="o", markersize=3.0,
            markerfacecolor="#8C564B", markeredgewidth=0.0, alpha=0.9,
            label="Estimated",
        )
        if u_eff is not None and len(u_eff) == len(x_est):
            ue = np.abs(u_eff[m1e][order])
            valid_u = np.isfinite(ue)
            if np.any(valid_u):
                axes[2].fill_between(
                    xe[valid_u], ye[valid_u] - ue[valid_u], ye[valid_u] + ue[valid_u],
                    color="#8C564B", alpha=0.16, linewidth=0.0, label="Estimated ± uncertainty",
                )

    # Best dictionary distance (same concept as STEP 4.2 distance-vs-time).
    y_dist = (
        pd.to_numeric(merged_df.get("best_distance"), errors="coerce").to_numpy(dtype=float)
        if "best_distance" in merged_df.columns
        else np.full(len(x_est), np.nan, dtype=float)
    )
    m_dist = np.isfinite(x_est) & np.isfinite(y_dist)
    if np.any(m_dist):
        order = np.argsort(x_est[m_dist])
        xd = x_est[m_dist][order]
        yd = y_dist[m_dist][order]
        axes[0].plot(
            xd,
            yd,
            color="#9467BD",
            linewidth=1.05,
            linestyle="-",
            marker="o",
            markersize=2.6,
            markerfacecolor="#9467BD",
            markeredgewidth=0.0,
            alpha=0.9,
            label="Best dictionary distance (best_distance)",
        )
        _apply_mean_striped_background(axes[0], yd)
        axes[0].legend(loc="best", fontsize=8)
    else:
        axes[0].text(0.5, 0.5, "No finite best_distance values", ha="center", va="center")
    axes[0].set_ylabel("best_distance")
    axes[0].set_title("Best dictionary distance vs time")
    axes[0].grid(True, alpha=0.25)

    axes[1].set_ylabel("flux_cm2_min")
    axes[1].set_title("Flux: complete + discretized + STEP 3.2 center + estimated")
    _apply_mean_striped_background(axes[1], np.concatenate(flux_stripe_vals))
    axes[1].grid(True, alpha=0.25)
    axes[1].legend(loc="best", fontsize=8)

    axes[2].set_ylabel("eff")
    axes[2].set_xlabel(x_label)
    axes[2].set_title("Efficiency: complete + discretized + STEP 3.2 center + estimated")
    _apply_mean_striped_background(axes[2], np.concatenate(eff_stripe_vals))
    axes[2].grid(True, alpha=0.25)
    axes[2].legend(loc="best", fontsize=8)

    fig.tight_layout()
    _save_figure(fig, path, dpi=160)
    plt.close(fig)


def _plot_flux_recovery_vs_global_rate(
    *,
    df: pd.DataFrame,
    complete_df: pd.DataFrame | None,
    flux_complete_col: str,
    eff_complete_col: str,
    flux_true_col: str,
    eff_true_col: str,
    flux_est_col: str,
    flux_unc_abs_col: str | None,
    global_rate_col: str,
    eff_plot_cols: list[str] | None,
    path: Path,
) -> None:
    """Plot feature-space distance, global rate, efficiencies, and flux."""
    def _apply_striped_background(ax: plt.Axes, y_vals: np.ndarray) -> None:
        """Apply stripes at 1%-of-mean increments, uniformly across the y-axis."""
        y_min, y_max = ax.get_ylim()
        if not (np.isfinite(y_min) and np.isfinite(y_max)):
            return
        span = y_max - y_min
        if span <= 0.0:
            return

        valid = np.isfinite(y_vals)
        if not np.any(valid):
            return
        mean_val = float(np.mean(y_vals[valid]))

        band = abs(mean_val) * 0.01
        if not np.isfinite(band) or band <= 0.0:
            band = span * 0.01
        if band <= 0.0:
            return

        ax.set_facecolor("#FFFFFF")
        idx = int(np.floor((y_min - mean_val) / band))
        y0 = mean_val + idx * band
        while y0 < y_max:
            y1 = y0 + band
            lo = max(y0, y_min)
            hi = min(y1, y_max)
            color = "#FFFFFF" if (idx % 2 == 0) else "#D8DDE4"
            if hi > lo:
                ax.axhspan(lo, hi, facecolor=color, alpha=1.0, linewidth=0.0, zorder=0)
            y0 = y1
            idx += 1
        ax.set_ylim(y_min, y_max)

    from matplotlib.ticker import FuncFormatter, MaxNLocator

    def _eff_display_name(col: str) -> str:
        text = str(col).strip()
        if text.startswith("eff_sim_"):
            idx = text.split("_")[-1]
            return f"Eff {idx}"
        return text.replace("_", " ")

    x, x_label = _time_axis(df)
    true_flux = pd.to_numeric(df.get(flux_true_col), errors="coerce").to_numpy(dtype=float)
    est_flux = pd.to_numeric(df.get(flux_est_col), errors="coerce").to_numpy(dtype=float)
    rate_vals = pd.to_numeric(df.get(global_rate_col), errors="coerce").to_numpy(dtype=float)
    unc_flux = (
        pd.to_numeric(df.get(flux_unc_abs_col), errors="coerce").to_numpy(dtype=float)
        if flux_unc_abs_col and flux_unc_abs_col in df.columns
        else None
    )

    # Prefer complete-curve references for simulated flux/efficiency.
    x_ref_flux = x
    y_ref_flux = true_flux
    ref_flux_label = "Simulated flux (discretized)"
    if complete_df is not None and not complete_df.empty:
        if flux_complete_col in complete_df.columns:
            xc, _ = _time_axis(complete_df)
            yc = pd.to_numeric(complete_df.get(flux_complete_col), errors="coerce").to_numpy(dtype=float)
            if len(xc) == len(yc):
                x_ref_flux = xc
                y_ref_flux = yc
                ref_flux_label = "Simulated flux (complete)"

    # Prefer complete-curve references for global rate when available.
    x_ref_rate = x
    y_ref_rate = np.full(len(x), np.nan, dtype=float)
    if complete_df is not None and not complete_df.empty:
        for c in ("events_per_second_global_rate", "global_rate_hz_mean", "global_rate_hz_mid"):
            if c in complete_df.columns:
                xc, _ = _time_axis(complete_df)
                yc = pd.to_numeric(complete_df.get(c), errors="coerce").to_numpy(dtype=float)
                if len(xc) == len(yc):
                    x_ref_rate = xc
                    y_ref_rate = yc
                    break

    dist_col: str | None = None
    for candidate in (
        "best_distance",
        "best_distance_base_l2",
        "stage2_best_distance_rate",
        "stage1_best_distance_eff",
    ):
        if candidate in df.columns:
            dist_col = candidate
            break
    if dist_col is None:
        for col in df.columns:
            name = str(col).lower()
            if "best_distance" in name:
                dist_col = str(col)
                break
    if dist_col is None:
        for col in df.columns:
            name = str(col).lower()
            if "distance" in name:
                dist_col = str(col)
                break

    fig, axes = plt.subplots(
        4,
        1,
        figsize=(11.6, 10.6),
        sharex=True,
        gridspec_kw={"height_ratios": [0.85, 1.0, 1.05, 1.25]},
    )
    for ax in axes:
        ax.set_facecolor("#FFFFFF")
        ax.grid(True, alpha=0.24)

    # 1) Feature-space distance quality metric.
    if dist_col is not None:
        dist_vals = pd.to_numeric(df.get(dist_col), errors="coerce").to_numpy(dtype=float)
    else:
        dist_vals = np.full(len(x), np.nan, dtype=float)
    m_dist = np.isfinite(x) & np.isfinite(dist_vals)
    if np.any(m_dist):
        order = np.argsort(x[m_dist])
        xs = x[m_dist][order]
        ys = dist_vals[m_dist][order]
        axes[0].plot(
            xs,
            ys,
            color="#6A3D9A",
            linewidth=2.1,
            alpha=0.95,
            solid_capstyle="round",
            label=(dist_col if dist_col is not None else "distance"),
        )
        _apply_striped_background(axes[0], ys)
        axes[0].legend(loc="best", fontsize=8, framealpha=0.92, facecolor="white")
    else:
        axes[0].text(0.5, 0.5, "No finite distance values", ha="center", va="center")
    axes[0].set_ylabel("Distance")
    axes[0].set_title(
        f"Feature-space distance (quality) [{dist_col}]"
        if dist_col is not None
        else "Feature-space distance (quality)"
    )

    # 2) Global rate.
    rate_bg: list[np.ndarray] = []
    m_rate = np.isfinite(x) & np.isfinite(rate_vals)
    if np.any(m_rate):
        order = np.argsort(x[m_rate])
        xs = x[m_rate][order]
        ys = rate_vals[m_rate][order]
        rate_bg.append(ys)
        axes[1].plot(
            xs,
            ys,
            color="#2E8B57",
            linewidth=2.6,
            alpha=0.95,
            solid_capstyle="round",
            label="Weighted global rate",
        )
    m_ref_rate = np.isfinite(x_ref_rate) & np.isfinite(y_ref_rate)
    if np.any(m_ref_rate):
        order = np.argsort(x_ref_rate[m_ref_rate])
        xs = x_ref_rate[m_ref_rate][order]
        ys = y_ref_rate[m_ref_rate][order]
        rate_bg.append(ys)
        axes[1].plot(
            xs,
            ys,
            color="#7FBF7B",
            linewidth=1.3,
            linestyle="--",
            alpha=0.92,
            label="Complete-curve rate reference",
        )
    axes[1].set_ylabel("Global rate [Hz]")
    axes[1].set_title("Global rate time series")
    if rate_bg:
        _apply_striped_background(axes[1], np.concatenate(rate_bg))
    axes[1].yaxis.set_major_locator(MaxNLocator(integer=True))
    axes[1].yaxis.set_major_formatter(FuncFormatter(lambda v, _pos: f"{int(np.rint(v))}"))
    axes[1].legend(loc="best", fontsize=8, framealpha=0.92, facecolor="white")

    # 3) Efficiencies: simulated vs estimated (all available planes).
    requested_eff_cols = [str(c).strip() for c in (eff_plot_cols or []) if str(c).strip()]
    fallback_eff_cols = ["eff_sim_1", "eff_sim_2", "eff_sim_3", "eff_sim_4"]
    eff_candidates = requested_eff_cols + fallback_eff_cols + [str(eff_complete_col).strip()]
    eff_base_from_true = (
        str(eff_true_col)[len("true_"):] if str(eff_true_col).startswith("true_") else str(eff_true_col)
    )
    if eff_base_from_true:
        eff_candidates.append(eff_base_from_true)

    eff_cols: list[str] = []
    for col in eff_candidates:
        if not col or col in eff_cols:
            continue
        if (
            (complete_df is not None and not complete_df.empty and col in complete_df.columns)
            or (f"true_{col}" in df.columns)
            or (col in df.columns)
            or (f"est_{col}" in df.columns)
            or (f"corrected_{col}" in df.columns)
        ):
            eff_cols.append(col)

    eff_palette = ["#1F77B4", "#FF7F0E", "#2CA02C", "#9467BD", "#8C564B", "#17BECF"]
    eff_bg: list[np.ndarray] = []
    eff_unc_legend_added = False
    for idx, eff_col in enumerate(eff_cols):
        color = eff_palette[idx % len(eff_palette)]
        eff_name = _eff_display_name(eff_col)

        # Simulated reference for this efficiency.
        x_sim = x
        y_sim = np.full(len(x), np.nan, dtype=float)
        y_true_col = f"true_{eff_col}"
        if y_true_col in df.columns:
            y_sim = pd.to_numeric(df.get(y_true_col), errors="coerce").to_numpy(dtype=float)
        elif eff_col in df.columns:
            y_sim = pd.to_numeric(df.get(eff_col), errors="coerce").to_numpy(dtype=float)
        elif eff_col == eff_base_from_true and eff_true_col in df.columns:
            y_sim = pd.to_numeric(df.get(eff_true_col), errors="coerce").to_numpy(dtype=float)
        if complete_df is not None and not complete_df.empty and eff_col in complete_df.columns:
            xc, _ = _time_axis(complete_df)
            yc = pd.to_numeric(complete_df.get(eff_col), errors="coerce").to_numpy(dtype=float)
            if len(xc) == len(yc):
                x_sim = xc
                y_sim = yc
        m_sim = np.isfinite(x_sim) & np.isfinite(y_sim)
        if np.any(m_sim):
            order = np.argsort(x_sim[m_sim])
            xs = x_sim[m_sim][order]
            ys = y_sim[m_sim][order]
            eff_bg.append(ys)
            axes[2].plot(
                xs,
                ys,
                color=color,
                linewidth=1.15,
                linestyle="--",
                alpha=0.62,
                label=f"{eff_name} sim",
            )

        # Estimated series for this efficiency.
        est_eff_col = (
            f"corrected_{eff_col}" if f"corrected_{eff_col}" in df.columns
            else (f"est_{eff_col}" if f"est_{eff_col}" in df.columns else None)
        )
        if est_eff_col is None:
            continue
        y_est = pd.to_numeric(df.get(est_eff_col), errors="coerce").to_numpy(dtype=float)
        m_est = np.isfinite(x) & np.isfinite(y_est)
        if np.any(m_est):
            order = np.argsort(x[m_est])
            xs = x[m_est][order]
            ys = y_est[m_est][order]
            eff_bg.append(ys)
            axes[2].plot(
                xs,
                ys,
                color=color,
                linewidth=1.9,
                linestyle="-",
                alpha=0.97,
                marker="o",
                markersize=2.7,
                markerfacecolor=color,
                markeredgecolor="white",
                markeredgewidth=0.35,
                label=f"{eff_name} est",
            )
            unc_col = f"unc_{eff_col}_abs"
            if unc_col in df.columns:
                ue = np.abs(pd.to_numeric(df.get(unc_col), errors="coerce").to_numpy(dtype=float)[m_est][order])
                valid_u = np.isfinite(ue)
                if np.any(valid_u):
                    axes[2].fill_between(
                        xs[valid_u],
                        ys[valid_u] - ue[valid_u],
                        ys[valid_u] + ue[valid_u],
                        color=color,
                        alpha=0.12,
                        linewidth=0.0,
                        label=("Estimated ± uncertainty" if not eff_unc_legend_added else None),
                    )
                    eff_unc_legend_added = True

    axes[2].set_ylabel("Efficiency")
    axes[2].set_title("Efficiencies: simulated vs estimated")
    if eff_bg:
        _apply_striped_background(axes[2], np.concatenate(eff_bg))
    axes[2].legend(
        loc="best",
        fontsize=7,
        ncol=4,
        framealpha=0.92,
        facecolor="white",
        columnspacing=1.1,
        handlelength=2.2,
    )

    # 4) Flux: simulated vs estimated (same color family; style separates curves).
    flux_color = "#D62728"
    m_true_flux = np.isfinite(x_ref_flux) & np.isfinite(y_ref_flux)
    if np.any(m_true_flux):
        order = np.argsort(x_ref_flux[m_true_flux])
        xs = x_ref_flux[m_true_flux][order]
        ys = y_ref_flux[m_true_flux][order]
        axes[3].plot(
            xs,
            ys,
            color=flux_color,
            linewidth=1.4,
            linestyle="--",
            alpha=0.58,
            label="Simulated flux",
            zorder=1,
        )

    m_est_flux = np.isfinite(x) & np.isfinite(est_flux)
    flux_bg = [y_ref_flux, est_flux]
    if np.any(m_est_flux):
        order = np.argsort(x[m_est_flux])
        xe = x[m_est_flux][order]
        ye = est_flux[m_est_flux][order]
        axes[3].plot(
            xe,
            ye,
            color=flux_color,
            linewidth=2.8,
            marker="o",
            markersize=4.4,
            markerfacecolor=flux_color,
            markeredgecolor="white",
            markeredgewidth=0.45,
            alpha=0.99,
            label="Estimated flux",
            zorder=3,
        )
        if unc_flux is not None and len(unc_flux) == len(x):
            ue = np.abs(np.asarray(unc_flux, dtype=float)[m_est_flux][order])
            valid_ue = np.isfinite(ue)
            if np.any(valid_ue):
                axes[3].fill_between(
                    xe[valid_ue],
                    ye[valid_ue] - ue[valid_ue],
                    ye[valid_ue] + ue[valid_ue],
                    color=flux_color,
                    alpha=0.14,
                    linewidth=0.0,
                    label="Estimated ± uncertainty",
                    zorder=2,
                )
    axes[3].set_ylabel("Flux")
    axes[3].set_xlabel(x_label)
    axes[3].set_title("Flux: simulated vs estimated")
    _apply_striped_background(axes[3], np.concatenate([arr for arr in flux_bg if arr.size > 0]))
    axes[3].legend(loc="best", fontsize=8, framealpha=0.92, facecolor="white")

    fig.suptitle(
        "Feature-space quality and reconstruction diagnostics",
        fontsize=11,
    )

    fig.tight_layout()
    _save_figure(fig, path, dpi=170)
    plt.close(fig)


def _plot_corrected_time_series_overview(
    *,
    complete_df: pd.DataFrame | None,
    time_df: pd.DataFrame,
    merged_df: pd.DataFrame,
    flux_col: str,
    eff_cols: list[str],
    corrected_flux_col: str,
    flux_unc_abs_col: str | None,
    global_rate_col: str | None,
    path: Path,
) -> None:
    """Plot weighted-vs-corrected trajectory for flux, all efficiencies, and global rate."""
    fig, axes = plt.subplots(3, 1, figsize=(11.8, 9.4), sharex=True)
    x_merge, x_label = _time_axis(merged_df)
    x_time, _ = _time_axis(time_df)
    x_complete, _ = _time_axis(complete_df) if complete_df is not None and not complete_df.empty else (None, "")

    # Panel 1: flux.
    flux_bg: list[np.ndarray] = []
    y_weighted_flux = pd.to_numeric(merged_df.get(flux_col), errors="coerce").to_numpy(dtype=float)
    y_corrected_flux = pd.to_numeric(merged_df.get(corrected_flux_col), errors="coerce").to_numpy(dtype=float)
    flux_bg.extend([y_weighted_flux, y_corrected_flux])
    m_wf = np.isfinite(x_merge) & np.isfinite(y_weighted_flux)
    if np.any(m_wf):
        axes[0].scatter(
            x_merge[m_wf],
            y_weighted_flux[m_wf],
            s=16,
            facecolors="white",
            edgecolors="#1F77B4",
            linewidths=0.8,
            label="Weighted curve (STEP 3.2)",
            zorder=2,
        )
    m_cf = np.isfinite(x_merge) & np.isfinite(y_corrected_flux)
    if np.any(m_cf):
        order = np.argsort(x_merge[m_cf])
        xs = x_merge[m_cf][order]
        ys = y_corrected_flux[m_cf][order]
        axes[0].plot(
            xs,
            ys,
            color="#D62728",
            linewidth=1.15,
            linestyle="-",
            label="Corrected curve (STEP 3.3)",
            zorder=3,
        )
        if flux_unc_abs_col and flux_unc_abs_col in merged_df.columns:
            unc = pd.to_numeric(merged_df.get(flux_unc_abs_col), errors="coerce").to_numpy(dtype=float)
            if len(unc) == len(x_merge):
                us = np.abs(unc[m_cf][order])
                valid_u = np.isfinite(us)
                if np.any(valid_u):
                    axes[0].fill_between(
                        xs[valid_u],
                        ys[valid_u] - us[valid_u],
                        ys[valid_u] + us[valid_u],
                        color="#D62728",
                        alpha=0.16,
                        linewidth=0.0,
                        label="Corrected ± uncertainty",
                        zorder=1,
                    )
    if complete_df is not None and not complete_df.empty and flux_col in complete_df.columns and x_complete is not None:
        y_complete_flux = pd.to_numeric(complete_df.get(flux_col), errors="coerce").to_numpy(dtype=float)
        flux_bg.append(y_complete_flux)
        m_comp = np.isfinite(x_complete) & np.isfinite(y_complete_flux)
        if np.any(m_comp):
            axes[0].plot(
                x_complete[m_comp],
                y_complete_flux[m_comp],
                color="#1F77B4",
                linewidth=0.95,
                linestyle="--",
                alpha=0.60,
                label="Complete curve (STEP 3.1)",
                zorder=0,
            )
    axes[0].set_ylabel("flux_cm2_min")
    axes[0].set_title("Flux: weighted (STEP 3.2) vs corrected (STEP 3.3)")
    _apply_mean_striped_background(axes[0], np.concatenate(flux_bg))
    axes[0].grid(True, alpha=0.25)
    axes[0].legend(loc="best", fontsize=8)

    # Panel 2: all efficiencies in one plot.
    eff_palette = ["#FF7F0E", "#D62728", "#9467BD", "#8C564B", "#2CA02C", "#17BECF"]
    eff_bg: list[np.ndarray] = []
    complete_label_added = False
    for idx, eff_col in enumerate(eff_cols):
        color = eff_palette[idx % len(eff_palette)]
        weighted = pd.to_numeric(merged_df.get(eff_col), errors="coerce").to_numpy(dtype=float)
        corrected_col = f"corrected_{eff_col}" if f"corrected_{eff_col}" in merged_df.columns else f"est_{eff_col}"
        if corrected_col not in merged_df.columns:
            continue
        corrected = pd.to_numeric(merged_df.get(corrected_col), errors="coerce").to_numpy(dtype=float)
        eff_bg.extend([weighted, corrected])

        if complete_df is not None and not complete_df.empty and eff_col in complete_df.columns and x_complete is not None:
            y_comp = pd.to_numeric(complete_df.get(eff_col), errors="coerce").to_numpy(dtype=float)
            eff_bg.append(y_comp)
            m_comp = np.isfinite(x_complete) & np.isfinite(y_comp)
            if np.any(m_comp):
                axes[1].plot(
                    x_complete[m_comp],
                    y_comp[m_comp],
                    color=color,
                    linewidth=0.85,
                    linestyle="--",
                    alpha=0.45,
                    label=("Complete curve (STEP 3.1)" if not complete_label_added else None),
                    zorder=0,
                )
                complete_label_added = True

        m_w = np.isfinite(x_merge) & np.isfinite(weighted)
        if np.any(m_w):
            axes[1].scatter(
                x_merge[m_w],
                weighted[m_w],
                s=14,
                facecolors="white",
                edgecolors=color,
                linewidths=0.75,
                label=f"{eff_col} weighted",
                zorder=2,
            )

        m_c = np.isfinite(x_merge) & np.isfinite(corrected)
        if np.any(m_c):
            order = np.argsort(x_merge[m_c])
            xs = x_merge[m_c][order]
            ys = corrected[m_c][order]
            axes[1].plot(
                xs,
                ys,
                color=color,
                linewidth=1.05,
                linestyle="-",
                alpha=0.92,
                label=f"{eff_col} corrected",
                zorder=3,
            )
            unc_col = f"unc_{eff_col}_abs"
            if unc_col in merged_df.columns:
                unc = pd.to_numeric(merged_df.get(unc_col), errors="coerce").to_numpy(dtype=float)
                if len(unc) == len(x_merge):
                    us = np.abs(unc[m_c][order])
                    valid_u = np.isfinite(us)
                    if np.any(valid_u):
                        axes[1].fill_between(
                            xs[valid_u],
                            ys[valid_u] - us[valid_u],
                            ys[valid_u] + us[valid_u],
                            color=color,
                            alpha=0.08,
                            linewidth=0.0,
                            zorder=1,
                        )

    axes[1].set_ylabel("eff")
    axes[1].set_title("Efficiencies (all planes): weighted (STEP 3.2) vs corrected (STEP 3.3)")
    if eff_bg:
        _apply_mean_striped_background(axes[1], np.concatenate(eff_bg))
    axes[1].grid(True, alpha=0.25)
    axes[1].legend(loc="best", fontsize=7, ncol=2)

    # Panel 3: global rate (feature-space output from STEP 3.2).
    rate_bg: list[np.ndarray] = []
    rate_col_merge = None
    for c in (
        global_rate_col,
        "events_per_second_global_rate",
        "global_rate_hz_mean",
        "global_rate_hz_mid",
    ):
        if c and c in merged_df.columns:
            rate_col_merge = c
            break
    if rate_col_merge is not None:
        y_rate_merge = pd.to_numeric(merged_df.get(rate_col_merge), errors="coerce").to_numpy(dtype=float)
        rate_bg.append(y_rate_merge)
        m_rm = np.isfinite(x_merge) & np.isfinite(y_rate_merge)
        if np.any(m_rm):
            axes[2].plot(
                x_merge[m_rm],
                y_rate_merge[m_rm],
                color="#2CA02C",
                linewidth=1.1,
                linestyle="-",
                label=f"Weighted feature-space rate ({rate_col_merge})",
            )

    rate_col_time = None
    for c in ("events_per_second_global_rate", "global_rate_hz_mean", "global_rate_hz_mid"):
        if c in time_df.columns:
            rate_col_time = c
            break
    if rate_col_time is not None:
        y_rate_time = pd.to_numeric(time_df.get(rate_col_time), errors="coerce").to_numpy(dtype=float)
        rate_bg.append(y_rate_time)
        m_rt = np.isfinite(x_time) & np.isfinite(y_rate_time)
        if np.any(m_rt):
            axes[2].scatter(
                x_time[m_rt],
                y_rate_time[m_rt],
                s=16,
                facecolors="white",
                edgecolors="#2CA02C",
                linewidths=0.8,
                label="Discretized rate (STEP 3.1)",
            )

    if complete_df is not None and not complete_df.empty and x_complete is not None:
        rate_col_complete = None
        for c in ("events_per_second_global_rate", "global_rate_hz_mean", "global_rate_hz_mid"):
            if c in complete_df.columns:
                rate_col_complete = c
                break
        if rate_col_complete is not None:
            y_rate_complete = pd.to_numeric(complete_df.get(rate_col_complete), errors="coerce").to_numpy(dtype=float)
            rate_bg.append(y_rate_complete)
            m_rc = np.isfinite(x_complete) & np.isfinite(y_rate_complete)
            if np.any(m_rc):
                axes[2].plot(
                    x_complete[m_rc],
                    y_rate_complete[m_rc],
                    color="#2CA02C",
                    linewidth=0.9,
                    linestyle="--",
                    alpha=0.6,
                    label="Complete rate (STEP 3.1)",
                )

    axes[2].set_xlabel(x_label)
    axes[2].set_ylabel("global rate [Hz]")
    axes[2].set_title("Global rate (feature-space dimension, carried from STEP 3.2)")
    if rate_bg:
        _apply_mean_striped_background(axes[2], np.concatenate(rate_bg))
    axes[2].grid(True, alpha=0.25)
    axes[2].legend(loc="best", fontsize=8)

    fig.tight_layout()
    _save_figure(fig, path, dpi=170)
    plt.close(fig)


def _plot_corrected_parameter_space_lower_triangle(
    *,
    dictionary_df: pd.DataFrame,
    merged_df: pd.DataFrame,
    complete_df: pd.DataFrame | None,
    parameter_space_cols: list[str],
    path: Path,
) -> None:
    """Lower-triangular parameter-space diagnostics for weighted and corrected curves."""
    n = len(parameter_space_cols)
    if n <= 0:
        return

    fig, axes = plt.subplots(n, n, figsize=(3.1 * n, 3.1 * n), squeeze=False)

    for i, y_col in enumerate(parameter_space_cols):
        for j, x_col in enumerate(parameter_space_cols):
            ax = axes[i, j]
            if i < j:
                ax.axis("off")
                continue

            bx = pd.to_numeric(dictionary_df.get(x_col), errors="coerce")
            by = pd.to_numeric(dictionary_df.get(y_col), errors="coerce")
            wx = pd.to_numeric(merged_df.get(x_col), errors="coerce")
            wy = pd.to_numeric(merged_df.get(y_col), errors="coerce")

            cx_col = f"corrected_{x_col}" if f"corrected_{x_col}" in merged_df.columns else f"est_{x_col}"
            cy_col = f"corrected_{y_col}" if f"corrected_{y_col}" in merged_df.columns else f"est_{y_col}"
            cx = pd.to_numeric(merged_df.get(cx_col), errors="coerce")
            cy = pd.to_numeric(merged_df.get(cy_col), errors="coerce")

            if i == j:
                b = bx.dropna()
                w = wx.dropna()
                c = cx.dropna()
                if not b.empty:
                    ax.hist(b, bins=34, color="#808080", alpha=0.34, label="Dictionary")
                if not w.empty:
                    ax.hist(w, bins=34, color="#1F77B4", alpha=0.30, label="Weighted curve")
                if not c.empty:
                    ax.hist(c, bins=34, color="#D62728", alpha=0.30, label="Corrected curve")
                if i == 0 and j == 0:
                    ax.legend(loc="best", fontsize=7)
                ax.set_ylabel("count")
            else:
                m_basis = bx.notna() & by.notna()
                if m_basis.any():
                    ax.scatter(
                        bx[m_basis],
                        by[m_basis],
                        s=6,
                        color="#7A7A7A",
                        alpha=0.16,
                        linewidths=0,
                        label=("Dictionary" if (i == 1 and j == 0) else None),
                        zorder=1,
                    )

                if complete_df is not None and not complete_df.empty:
                    kx = pd.to_numeric(complete_df.get(x_col), errors="coerce")
                    ky = pd.to_numeric(complete_df.get(y_col), errors="coerce")
                    m_comp = kx.notna() & ky.notna()
                    if m_comp.any():
                        ax.plot(
                            kx[m_comp],
                            ky[m_comp],
                            color="#1F77B4",
                            lw=0.95,
                            alpha=0.55,
                            linestyle="--",
                            label=("Complete curve" if (i == 1 and j == 0) else None),
                            zorder=2,
                        )

                m_weighted = wx.notna() & wy.notna()
                if m_weighted.any():
                    ax.scatter(
                        wx[m_weighted],
                        wy[m_weighted],
                        s=14,
                        facecolor="white",
                        edgecolor="black",
                        linewidth=0.5,
                        label=("Weighted curve" if (i == 1 and j == 0) else None),
                        zorder=3,
                    )

                m_corr = cx.notna() & cy.notna()
                if m_corr.any():
                    ax.plot(
                        cx[m_corr],
                        cy[m_corr],
                        color="#D62728",
                        lw=1.05,
                        alpha=0.92,
                        linestyle="-",
                        label=("Corrected curve" if (i == 1 and j == 0) else None),
                        zorder=4,
                    )

            ax.grid(True, alpha=0.20)
            if i == n - 1:
                ax.set_xlabel(x_col)
            else:
                ax.set_xticklabels([])
            if j == 0 and i > 0:
                ax.set_ylabel(y_col)
            elif i > 0:
                ax.set_yticklabels([])

    if n >= 2:
        handles, labels = axes[1, 0].get_legend_handles_labels()
        if handles:
            fig.legend(handles, labels, loc="upper right", fontsize=8, framealpha=0.9)
    fig.suptitle("STEP 3.3 corrected curve in parameter space (lower triangle)", fontsize=12)
    fig.tight_layout(rect=[0.0, 0.0, 1.0, 0.98])
    _save_figure(fig, path, dpi=175)
    plt.close(fig)


_TT_BREAKDOWN_LABELS = (
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


def _resolve_tt_rate_breakdown_entries(
    df: pd.DataFrame,
) -> list[tuple[str, str, str]]:
    """Resolve TT-specific physical rate columns for the breakdown plot."""
    _selected_prefix, rate_cols_by_label = resolve_physical_tt_rate_columns(
        df,
        tt_labels=PHYSICAL_TT_RATE_LABELS,
        prefix_selector="last",
        include_to_tt_rate_hz=False,
        require_numeric=True,
    )

    tt_entries: list[tuple[str, str, str]] = []
    for tt_label in _TT_BREAKDOWN_LABELS:
        tt_rate_col = rate_cols_by_label.get(tt_label)
        if tt_rate_col is None:
            continue
        tt_entries.append((tt_label, tt_rate_col, "tt_specific"))
    return tt_entries


def _plot_tt_rate_breakdown(df: pd.DataFrame) -> int:
    """Plot TT-specific physical rate time series only."""
    x, x_label = _time_axis(df)

    tt_entries = _resolve_tt_rate_breakdown_entries(df)

    if not tt_entries:
        return 0

    n_tt = len(tt_entries)
    fig, axes = plt.subplots(
        1, n_tt,
        figsize=(4.0 * n_tt, 3.3),
        squeeze=False,
    )

    for col in range(1, n_tt):
        axes[0, col].sharey(axes[0, 0])

    colors = ["#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B3"]
    for j, (tt_label, rate_col, _rate_source) in enumerate(tt_entries):
        rate = pd.to_numeric(df[rate_col], errors="coerce").to_numpy(dtype=float)
        color = colors[j % len(colors)]

        ax = axes[0, j]
        ok = np.isfinite(rate)
        if ok.any():
            ax.scatter(x[ok], rate[ok], s=8, color=color, alpha=0.6, edgecolors="none")
        else:
            ax.text(0.5, 0.5, "No rate values", ha="center", va="center", transform=ax.transAxes, fontsize=7.5)
        ax.set_title(f"TT {tt_label}", fontsize=9, fontweight="bold")
        ax.grid(True, alpha=0.2, linewidth=0.5)

    axes[0, 0].set_ylabel("TT rate [Hz]", fontsize=8)
    for col in range(n_tt):
        axes[0, col].set_xlabel(x_label, fontsize=7)
        if col > 0:
            plt.setp(axes[0, col].get_yticklabels(), visible=False)
    fig.tight_layout()
    _save_figure(fig, PLOTS_DIR / "tt_rate_breakdown.png", dpi=170)
    plt.close(fig)
    return n_tt


def _make_plots(
    df: pd.DataFrame,
    *,
    parameter_space_cols: list[str],
) -> None:
    """Generate correction overview for the resolved parameter-space dimensions."""
    x, x_label = _time_axis(df)
    panels = _build_parameter_diagnostic_panels(df, parameter_space_cols=parameter_space_cols)
    if not panels:
        fig, ax = plt.subplots(figsize=(10.4, 4.8))
        ax.axis("off")
        ax.text(0.5, 0.58, "STEP 3.3 correction diagnostics", ha="center", va="center", fontsize=12, fontweight="bold")
        ax.text(0.5, 0.40, "No parameter-space dimensions with both true and estimated values were available.", ha="center", va="center", fontsize=10)
        fig.tight_layout()
        _save_figure(fig, PLOTS_DIR / "correction_overview.png", dpi=160)
        plt.close(fig)
        return

    n_rows = len(panels)
    fig_h = max(8.5, 3.1 * n_rows)
    fig, axes = plt.subplots(n_rows, 2, figsize=(13.2, fig_h), squeeze=False, sharey="row")
    for row, (base, true_vals, est_vals, unc_abs) in enumerate(panels):
        _plot_series_panel(
            axes[row, 0],
            x=x,
            true_vals=true_vals,
            est_vals=est_vals,
            unc_abs=unc_abs,
            ylabel=base,
            title=f"{base} time series",
        )
        _plot_diag_panel(
            axes[row, 1],
            true_vals=true_vals,
            est_vals=est_vals,
            unc_abs=unc_abs,
            xlabel=f"True {base}",
            ylabel=f"Estimated {base}",
            title=f"{base} diagonal (y = x)",
        )

    axes[n_rows - 1, 0].set_xlabel(x_label)
    fig.suptitle("STEP 3.3 correction diagnostics", fontsize=12)
    fig.tight_layout()
    _save_figure(fig, PLOTS_DIR / "correction_overview.png", dpi=160)
    plt.close(fig)


def main() -> int:
    """Run STEP 3.3 correction workflow."""
    parser = argparse.ArgumentParser(
        description="Step 3.3: Apply dictionary inference + LUT uncertainty to synthetic dataset."
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--synthetic-csv", default=None)
    parser.add_argument("--dictionary-csv", default=None)
    parser.add_argument("--lut-csv", default=None)
    parser.add_argument("--lut-meta-json", default=None)
    args = parser.parse_args()

    config = _load_config(Path(args.config))
    _clear_plots_dir()
    cfg_21_raw = config.get("step_2_1", {})
    if not isinstance(cfg_21_raw, dict):
        cfg_21_raw = {}
    cfg_21, feature_cfg_sources = _merge_common_feature_space_cfg(config, cfg_21_raw)
    cfg_32 = config.get("step_3_2", {})
    cfg_33 = config.get("step_3_3", {})

    synthetic_csv_cfg = cfg_33.get("synthetic_dataset_csv", None)
    time_series_csv_cfg = cfg_33.get("time_series_csv", cfg_32.get("time_series_csv", None))
    complete_curve_csv_cfg = cfg_33.get("complete_curve_csv", cfg_32.get("complete_curve_csv", None))
    dictionary_csv_cfg = cfg_33.get("dictionary_csv", None)
    dataset_template_csv_cfg = cfg_33.get("dataset_template_csv", cfg_32.get("dataset_template_csv", None))
    lut_csv_cfg = cfg_33.get("uncertainty_lut_csv", None)
    lut_meta_cfg = cfg_33.get("uncertainty_lut_meta_json", None)
    build_summary_cfg = cfg_33.get("build_summary_json", None)
    step32_center_csv_cfg = cfg_33.get(
        "step32_diagnostic_center_csv",
        cfg_32.get("diagnostic_center_series_csv", None),
    )

    synthetic_path = _resolve_input_path(args.synthetic_csv or synthetic_csv_cfg or DEFAULT_SYNTHETIC_DATASET)
    time_series_path = _resolve_input_path(time_series_csv_cfg or DEFAULT_TIME_SERIES)
    complete_curve_path = _resolve_input_path(complete_curve_csv_cfg or DEFAULT_COMPLETE_CURVE)
    dictionary_path = _resolve_input_path(args.dictionary_csv or dictionary_csv_cfg or DEFAULT_DICTIONARY)
    dataset_template_path = _resolve_input_path(dataset_template_csv_cfg or DEFAULT_DATASET_TEMPLATE)
    lut_path = _resolve_input_path(args.lut_csv or lut_csv_cfg or DEFAULT_LUT)
    lut_meta_path = _resolve_input_path(args.lut_meta_json or lut_meta_cfg or DEFAULT_LUT_META)
    build_summary_path = _resolve_input_path(build_summary_cfg or DEFAULT_BUILD_SUMMARY)
    step32_center_path = _resolve_input_path(step32_center_csv_cfg or DEFAULT_STEP32_DIAGNOSTIC_CENTER)
    parameter_space_spec_cfg = cfg_33.get("parameter_space_columns_json", None)
    parameter_space_spec_path = _resolve_input_path(parameter_space_spec_cfg or DEFAULT_PARAMETER_SPACE_SPEC)

    for label, p in (
        ("Synthetic dataset", synthetic_path),
        ("Dictionary", dictionary_path),
        ("Uncertainty LUT", lut_path),
    ):
        if not p.exists():
            log.error("%s CSV not found: %s", label, p)
            return 1

    feature_columns_cfg = cfg_21.get("feature_columns", "auto")
    selected_feature_columns_path_cfg = cfg_21.get("selected_feature_columns_path", None)
    step12_selected_path = (
        _resolve_input_path(selected_feature_columns_path_cfg)
        if selected_feature_columns_path_cfg
        else DEFAULT_STEP12_SELECTED_FEATURE_COLUMNS
    )
    distance_metric = str(cfg_21.get("distance_metric", "l2_zscore"))
    interpolation_k_raw = cfg_21.get("interpolation_k", None)
    if interpolation_k_raw in (None, "", "null", "None"):
        interpolation_k: int | None = None
    else:
        interpolation_k = int(interpolation_k_raw)
    inverse_mapping_cfg_requested = cfg_21.get("inverse_mapping", {})
    include_global_rate = _safe_bool(cfg_21.get("include_global_rate", True), True)
    global_rate_col = str(cfg_21.get("global_rate_col", "events_per_second_global_rate"))
    exclude_same_file_cfg = _safe_bool(cfg_33.get("exclude_same_file", True), True)
    uncertainty_quantile = _safe_float(cfg_33.get("uncertainty_quantile", 0.68), 0.68)
    uncertainty_quantile = float(np.clip(uncertainty_quantile, 0.0, 1.0))

    if (
        cfg_32.get("flux_column") is not None
        or cfg_32.get("eff_column") is not None
        or config.get("step_3_1", {}).get("flux_column") is not None
        or config.get("step_3_1", {}).get("eff_column") is not None
    ):
        log.warning(
            "Deprecated keys step_3_2/step_3_1 flux_column/eff_column detected; ignored. "
            "STEP 3.3 now resolves parameter-space dimensions from STEP 1 artifacts instead.",
        )
    eff_pref = CANONICAL_EFF_COLUMN

    log.info("Synthetic dataset: %s", synthetic_path)
    log.info("Time series:      %s", time_series_path)
    log.info("Complete curve:   %s", complete_curve_path)
    log.info("Dictionary:       %s", dictionary_path)
    log.info("LUT:              %s", lut_path)
    log.info("STEP 1.3 fit summary: %s", build_summary_path)
    log.info("Metric=%s, k=%s, uncertainty_quantile=%.3f", distance_metric, interpolation_k, uncertainty_quantile)

    synthetic_df = pd.read_csv(synthetic_path, low_memory=False)
    if synthetic_df.empty:
        log.error("Synthetic dataset is empty: %s", synthetic_path)
        return 1
    dictionary_df = pd.read_csv(dictionary_path, low_memory=False)
    if dictionary_df.empty:
        log.error("Dictionary table is empty: %s", dictionary_path)
        return 1
    parameter_space_spec = _load_parameter_space_spec(parameter_space_spec_path)
    default_parameter_space_columns = _load_parameter_space_columns(parameter_space_spec_path)
    synthetic_df, synthetic_alias_cols = _apply_parameter_space_aliases(synthetic_df, parameter_space_spec)
    dictionary_df, dictionary_alias_cols = _apply_parameter_space_aliases(dictionary_df, parameter_space_spec)
    if synthetic_alias_cols or dictionary_alias_cols:
        log.info(
            "Applied STEP 1 parameter-space aliases: synthetic=%s dictionary=%s",
            synthetic_alias_cols,
            dictionary_alias_cols,
        )

    try:
        dict_work, synthetic_work, resolved_feature_columns, feature_strategy = _resolve_inference_feature_columns(
            feature_cfg=feature_columns_cfg,
            dict_df=dictionary_df,
            data_df=synthetic_df,
            include_global_rate=include_global_rate,
            global_rate_col=global_rate_col,
            step12_selected_path=step12_selected_path,
            derived_feature_cfg=cfg_21.get("derived_features", {}),
        )
    except ValueError as exc:
        log.error("%s", exc)
        return 1
    log.info(
        "Feature selection: strategy=%s selected=%d (config=%r, catalog=%s)",
        feature_strategy,
        len(resolved_feature_columns),
        feature_columns_cfg,
        CONFIG_COLUMNS_PATH,
    )
    if feature_cfg_sources.get("has_common_feature_space"):
        log.info(
            "Feature config source: common_feature_space keys=%s; step_2_1 overrides=%s",
            feature_cfg_sources.get("common_keys", []),
            feature_cfg_sources.get("step_2_1_override_keys", []),
        )
    if feature_strategy == "step12_selected":
        log.info("STEP 1.2 selected-feature artifact: %s", step12_selected_path)

    time_df = pd.DataFrame()
    if time_series_path.exists():
        time_df = pd.read_csv(time_series_path, low_memory=False)
    if time_df.empty:
        # Fallback to synthetic table for discretized trajectory.
        fallback_cols = [c for c in ("file_index", "elapsed_hours", "n_events") if c in synthetic_df.columns]
        time_df = synthetic_df[fallback_cols].copy()
    time_df, time_alias_cols = _apply_parameter_space_aliases(time_df, parameter_space_spec)

    complete_df = None
    if complete_curve_path.exists():
        tmp_complete = pd.read_csv(complete_curve_path, low_memory=False)
        complete_df = tmp_complete if not tmp_complete.empty else None
    complete_alias_cols: list[str] = []
    if complete_df is not None:
        complete_df, complete_alias_cols = _apply_parameter_space_aliases(complete_df, parameter_space_spec)
    if time_alias_cols or complete_alias_cols:
        log.info(
            "Applied STEP 1 parameter-space aliases: time=%s complete=%s",
            time_alias_cols,
            complete_alias_cols,
        )

    flux_col = _choose_flux_column(synthetic_df, CANONICAL_FLUX_COLUMN)
    try:
        eff_col = _choose_eff_column(synthetic_df, eff_pref)
    except KeyError:
        eff_col = None
    if flux_col is not None and flux_col not in time_df.columns:
        time_df[flux_col] = pd.to_numeric(synthetic_df.get(flux_col), errors="coerce")
    eff_col_time = None
    if eff_col is not None:
        try:
            eff_col_time = _choose_eff_column(time_df, eff_pref)
        except KeyError:
            eff_col_time = eff_col
            if eff_col in synthetic_df.columns:
                time_df[eff_col_time] = pd.to_numeric(synthetic_df.get(eff_col), errors="coerce")

    # ── Load STEP 1.5 distance definition ───────────────────────────
    try:
        dd, inverse_mapping_cfg, interpolation_k = resolve_runtime_distance_and_inverse_mapping(
            feature_columns=resolved_feature_columns,
            inverse_mapping_cfg=inverse_mapping_cfg_requested,
            interpolation_k=interpolation_k,
            context_label="STEP 3.3",
            distance_definition_path=PIPELINE_DIR / "STEP_1_SETUP" / "STEP_1_5_TUNE_DISTANCE_DEFINITION" / "OUTPUTS" / "FILES" / "distance_definition.json",
            logger=log,
        )
    except ValueError as exc:
        log.error("%s", exc)
        return 1
    if exclude_same_file_cfg:
        log.info(
            "Ignoring step_3_3.exclude_same_file=%s; using STEP 2.1 runtime behavior (exclude_same_file=false).",
            exclude_same_file_cfg,
        )
    log_runtime_inverse_mapping_summary(log, inverse_mapping_cfg)

    # ── 1) Inference over synthetic dataset ─────────────────────────
    parameter_space_cfg = cfg_33.get("parameter_space_columns", None)
    param_columns = _resolve_estimation_parameter_columns(
        dictionary_df=dict_work,
        configured_columns=parameter_space_cfg,
        default_columns=default_parameter_space_columns,
    )
    if not param_columns:
        log.error(
            "No parameter-space columns available for STEP 3.3 estimation (spec=%s).",
            parameter_space_spec_path,
        )
        return 1
    log.info("Parameter-space columns used for STEP 3.3 estimation: %s", param_columns)
    est_df = estimate_from_dataframes(
        dict_df=dict_work,
        data_df=synthetic_work,
        feature_columns=resolved_feature_columns,
        distance_metric=distance_metric,
        param_columns=param_columns,
        interpolation_k=interpolation_k,
        exclude_same_file=False,
        shared_parameter_exclusion_mode="full",
        shared_parameter_exclusion_columns=["param_set_id"],
        shared_parameter_exclusion_ignore=(),
        density_weighting_cfg=None,
        include_global_rate=False,
        global_rate_col=global_rate_col,
        inverse_mapping_cfg=inverse_mapping_cfg,
        distance_definition=dd,
    )

    # Merge with synthetic rows for time axes and true values.
    syn_with_idx = synthetic_df.copy()
    syn_with_idx["dataset_index"] = np.arange(len(syn_with_idx), dtype=int)
    merged = pd.merge(est_df, syn_with_idx, on="dataset_index", how="left", suffixes=("", "_synthetic"))

    # Explicit true/corrected columns for all inferred parameters.
    estimated_param_names: list[str] = []
    for col in est_df.columns:
        if str(col).startswith("est_"):
            pname = str(col)[len("est_"):]
            if pname and pname not in estimated_param_names:
                estimated_param_names.append(pname)

    for pname in estimated_param_names:
        est_name = f"est_{pname}"
        true_name = f"true_{pname}"
        if true_name in merged.columns:
            merged[true_name] = pd.to_numeric(merged.get(true_name), errors="coerce")
        elif pname in merged.columns:
            merged[true_name] = pd.to_numeric(merged.get(pname), errors="coerce")
        merged[f"corrected_{pname}"] = pd.to_numeric(merged.get(est_name), errors="coerce")

    # Preserve canonical true columns for downstream compatibility.
    if flux_col is not None and flux_col in merged.columns:
        merged[f"true_{flux_col}"] = pd.to_numeric(merged.get(flux_col), errors="coerce")
    if eff_col is not None and eff_col in merged.columns:
        merged[f"true_{eff_col}"] = pd.to_numeric(merged.get(eff_col), errors="coerce")
    if "n_events" in merged.columns:
        merged["n_events"] = pd.to_numeric(merged["n_events"], errors="coerce")
    elif "true_n_events" in merged.columns:
        merged["n_events"] = pd.to_numeric(merged["true_n_events"], errors="coerce")

    if estimated_param_names:
        log.info("Correction dimensions (estimated parameters): %s", estimated_param_names)

    # ── 2) LUT uncertainty interpolation ────────────────────────────
    lut_df = load_uncertainty_lut_table(lut_path)
    lut_params = detect_uncertainty_lut_param_names(
        lut_df,
        lut_meta_path if lut_meta_path.exists() else None,
    )
    lut_params = [p for p in lut_params if f"est_{p}" in merged.columns]
    if not lut_params:
        log.warning("No LUT parameter matches found in estimation output. Uncertainty columns will be NaN.")

    unc_df = interpolate_uncertainty_columns(
        query_df=merged,
        lut_df=lut_df,
        param_names=lut_params,
        quantile=uncertainty_quantile,
    )
    merged = pd.concat([merged, unc_df], axis=1)

    for pname in lut_params:
        est_col = f"est_{pname}"
        unc_pct_col = f"unc_{pname}_pct"
        unc_abs_col = f"unc_{pname}_abs"
        if est_col in merged.columns and unc_pct_col in merged.columns:
            # Convert percent uncertainty from LUT into absolute units.
            # Use |unc_pct| to keep uncertainty non-negative even if the LUT
            # was generated from a signed-error mode.
            est_v = pd.to_numeric(merged[est_col], errors="coerce").to_numpy(dtype=float)
            true_col = f"true_{pname}"
            true_v = (
                pd.to_numeric(merged.get(true_col), errors="coerce").to_numpy(dtype=float)
                if true_col in merged.columns else np.full(len(est_v), np.nan, dtype=float)
            )
            up = pd.to_numeric(merged[unc_pct_col], errors="coerce").to_numpy(dtype=float)

            # Prefer true-based conversion; fallback to estimate-based when true is
            # not available or too small to be meaningful (guard threshold matches validation denom).
            use_true = np.isfinite(true_v) & (np.abs(true_v) > 1e-9)
            abs_from_true = np.abs(true_v) * np.abs(up) / 100.0
            abs_from_est = np.abs(est_v) * np.abs(up) / 100.0
            abs_unc = np.where(use_true, abs_from_true, abs_from_est)

            # Ensure non-finite entries are explicit NaN
            abs_unc = np.where(np.isfinite(abs_unc), abs_unc, np.nan)
            merged[unc_abs_col] = abs_unc
        else:
            merged[unc_abs_col] = np.nan

    center_flux = None
    center_eff = None
    center_eff_col = None
    if flux_col is not None and eff_col_time is not None:
        center_flux, center_eff, center_eff_col = _compute_density_center_series(
            config=config,
            time_df=time_df,
            flux_col=flux_col,
            eff_pref=eff_pref,
            dictionary_path=dictionary_path,
            dataset_template_path=dataset_template_path,
        )
        if center_eff_col is not None:
            eff_col_time = center_eff_col

    correction_summary = {
        "enabled": True,
        "mode": "step_2_1_inverse_mapping",
        "description": (
            "Applied the same inverse-mapping correction used in STEP 2.1 "
            "to the STEP 3.2 weighted curve."
        ),
        "estimated_parameters": estimated_param_names,
        "corrected_column_prefix": "corrected_",
    }

    try:
        parameter_space_cols = _resolve_parameter_space_columns_from_cfg(
            merged_df=merged,
            dictionary_df=dictionary_df,
            configured_columns=parameter_space_cfg,
            default_columns=default_parameter_space_columns,
        )
    except KeyError as exc:
        log.warning("%s Falling back to estimated-parameter set.", exc)
        parameter_space_cols = [
            c for c in estimated_param_names
            if _find_estimated_parameter_column(merged, c) is not None
        ]

    parameter_metric_summary = _append_parameter_error_metrics(
        merged,
        parameter_space_cols=parameter_space_cols,
    )

    flux_param = next((c for c in parameter_space_cols if "flux" in str(c).lower()), None)
    eff_param = next((c for c in parameter_space_cols if _is_efficiency_parameter_column(c)), None)
    true_flux_col = _find_true_parameter_column(merged, flux_param) if flux_param else None
    true_eff_col = _find_true_parameter_column(merged, eff_param) if eff_param else None
    est_flux_col = _find_estimated_parameter_column(merged, flux_param) if flux_param else None
    est_eff_col = _find_estimated_parameter_column(merged, eff_param) if eff_param else None
    flux_unc_abs_col = f"unc_{flux_param}_abs" if flux_param and f"unc_{flux_param}_abs" in merged.columns else None
    eff_unc_abs_col = f"unc_{eff_param}_abs" if eff_param and f"unc_{eff_param}_abs" in merged.columns else None

    eff_cols_for_plot = [c for c in parameter_space_cols if _is_efficiency_parameter_column(c)]
    if not eff_cols_for_plot and eff_col is not None and eff_col in merged.columns:
        eff_cols_for_plot = [eff_col]

    global_rate_plot_col = None
    for c in (
        global_rate_col,
        f"true_{global_rate_col}",
        "events_per_second_global_rate",
        "global_rate_hz_mean",
        "global_rate_hz_mid",
        "true_events_per_second_global_rate",
    ):
        if c in merged.columns:
            global_rate_plot_col = c
            break

    if flux_param and f"error_{flux_param}" in merged.columns:
        merged["error_flux"] = merged[f"error_{flux_param}"]
        merged["relerr_flux_pct"] = merged.get(f"relerr_{flux_param}_pct")
        merged["abs_relerr_flux_pct"] = merged.get(f"abs_relerr_{flux_param}_pct")
    if eff_param and f"error_{eff_param}" in merged.columns:
        merged["error_eff"] = merged[f"error_{eff_param}"]
        merged["relerr_eff_pct"] = merged.get(f"relerr_{eff_param}_pct")
        merged["abs_relerr_eff_pct"] = merged.get(f"abs_relerr_{eff_param}_pct")
    step13_poly_correction_info = _append_step13_polynomial_efficiency_products(
        merged,
        build_summary_path=build_summary_path,
    )

    # ── Save outputs ────────────────────────────────────────────────
    out_csv = FILES_DIR / "corrected_by_inference.csv"
    merged.to_csv(out_csv, index=False)
    log.info("Wrote corrected table: %s (%d rows)", out_csv, len(merged))

    corrected_curve_cols: list[str] = []
    for c in (
        "dataset_index",
        "file_index",
        "time_start_utc",
        "time_end_utc",
        "time_utc",
        "elapsed_hours_start",
        "elapsed_hours_end",
        "elapsed_hours",
        "duration_seconds",
        "n_events",
    ):
        if c in merged.columns and c not in corrected_curve_cols:
            corrected_curve_cols.append(c)
    if global_rate_plot_col is not None and global_rate_plot_col in merged.columns:
        corrected_curve_cols.append(global_rate_plot_col)
    for pname in parameter_space_cols:
        for c in (
            pname,
            f"corrected_{pname}",
            f"est_{pname}",
            f"true_{pname}",
            f"unc_{pname}_abs",
            f"unc_{pname}_pct",
        ):
            if c in merged.columns and c not in corrected_curve_cols:
                corrected_curve_cols.append(c)
    for c in step13_poly_correction_info.get("application", {}).get("efficiency_columns_created", []):
        if c in merged.columns and c not in corrected_curve_cols:
            corrected_curve_cols.append(c)
    for c in step13_poly_correction_info.get("application", {}).get("efficiency_product_columns_created", []):
        if c in merged.columns and c not in corrected_curve_cols:
            corrected_curve_cols.append(c)
    corrected_curve_df = merged[corrected_curve_cols].copy()
    out_curve_csv = FILES_DIR / "corrected_curve.csv"
    corrected_curve_df.to_csv(out_curve_csv, index=False)
    log.info("Wrote corrected curve: %s (%d rows, %d cols)", out_curve_csv, len(corrected_curve_df), len(corrected_curve_df.columns))

    summary = {
        "synthetic_dataset_csv": str(synthetic_path),
        "dictionary_csv": str(dictionary_path),
        "uncertainty_lut_csv": str(lut_path),
        "corrected_table_csv": str(out_csv),
        "corrected_curve_csv": str(out_curve_csv),
        "overlay_center_source": "step_3_2_diagnostic_center_csv",
        "step32_diagnostic_center_csv": str(step32_center_path),
        "distance_metric": distance_metric,
        "distance_definition_used": dd.get("available", False),
        "distance_definition_mode": dd.get("selected_mode") if dd.get("available") else None,
        "interpolation_k": interpolation_k,
        "inverse_mapping": inverse_mapping_cfg,
        "parameter_space_spec_json": str(parameter_space_spec_path),
        "parameter_space_spec_columns_default": default_parameter_space_columns,
        "feature_columns_config": feature_columns_cfg,
        "feature_columns_strategy": feature_strategy,
        "feature_columns_resolved_count": int(len(resolved_feature_columns)),
        "feature_columns_resolved": resolved_feature_columns,
        "feature_columns_catalog": str(CONFIG_COLUMNS_PATH),
        "uncertainty_quantile": uncertainty_quantile,
        "n_rows": int(len(merged)),
        "n_successful_parameter_estimates": {
            pname: int(pd.to_numeric(merged.get(_find_estimated_parameter_column(merged, pname)), errors="coerce").notna().sum())
            for pname in parameter_space_cols
            if _find_estimated_parameter_column(merged, pname) is not None
        },
        "n_successful_flux_estimates": (
            int(pd.to_numeric(merged.get(est_flux_col), errors="coerce").notna().sum())
            if est_flux_col is not None
            else None
        ),
        "n_successful_eff_estimates": (
            int(pd.to_numeric(merged.get(est_eff_col), errors="coerce").notna().sum())
            if est_eff_col is not None
            else None
        ),
        "flux_true_col": true_flux_col,
        "flux_est_col": est_flux_col,
        "eff_true_col": true_eff_col,
        "eff_est_col": est_eff_col,
        "flux_unc_abs_col": flux_unc_abs_col,
        "eff_unc_abs_col": eff_unc_abs_col,
        "median_abs_relerr_flux_pct": _series_median_or_none(merged.get("abs_relerr_flux_pct")),
        "median_abs_relerr_eff_pct": _series_median_or_none(merged.get("abs_relerr_eff_pct")),
        "median_unc_flux_pct": (
            _series_median_or_none(merged.get(f"unc_{flux_param}_pct"))
            if flux_param and f"unc_{flux_param}_pct" in merged.columns else None
        ),
        "median_unc_eff_pct": (
            _series_median_or_none(merged.get(f"unc_{eff_param}_pct"))
            if eff_param and f"unc_{eff_param}_pct" in merged.columns else None
        ),
        "lut_param_names_used": lut_params,
        "density_center_available": bool(center_flux is not None and center_eff is not None),
        "correction_method": correction_summary,
        "step13_polynomial_efficiency_correction": step13_poly_correction_info,
        "parameter_space_columns_config": parameter_space_cfg,
        "parameter_space_columns_estimation": param_columns,
        "parameter_space_columns_used": parameter_space_cols,
        "parameter_space_metrics": parameter_metric_summary,
        "efficiency_columns_in_overview_plot": eff_cols_for_plot,
        "global_rate_column_used": global_rate_plot_col,
        "corrected_curve_columns": corrected_curve_cols,
    }
    out_summary = FILES_DIR / "correction_summary.json"
    with open(out_summary, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    log.info("Wrote summary: %s", out_summary)

    # ── Plots ───────────────────────────────────────────────────────
    for stale in (
        "diag_flux_true_vs_est.png",
        "diag_eff_true_vs_est.png",
        "estimated_vs_true_time_series.png",
    ):
        p = PLOTS_DIR / stale
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass

    _make_plots(
        merged,
        parameter_space_cols=parameter_space_cols,
    )
    _plot_tt_rate_breakdown(merged)
    corrected_flux_col = (
        f"corrected_{flux_col}"
        if flux_col is not None and f"corrected_{flux_col}" in merged.columns
        else est_flux_col
    )

    out_param_space = PLOTS_DIR / "parameter_space_lower_triangle_corrected.png"
    _plot_corrected_parameter_space_lower_triangle(
        dictionary_df=dictionary_df,
        merged_df=merged,
        complete_df=complete_df,
        parameter_space_cols=parameter_space_cols,
        path=out_param_space,
    )

    if global_rate_plot_col is None:
        log.warning(
            "Could not produce flux/global-rate plot: no global-rate column found (preferred: %s).",
            global_rate_col,
        )
    elif flux_col is None or est_flux_col is None or true_flux_col is None or eff_col_time is None or true_eff_col is None:
        missing = []
        if flux_col is None:
            missing.append("flux parameter")
        if est_flux_col is None:
            missing.append("estimated flux column")
        if true_flux_col is None:
            missing.append("true flux column")
        if eff_col_time is None:
            missing.append("time-series efficiency column")
        if true_eff_col is None:
            missing.append("true efficiency column")
        log.warning(
            "Skipping STEP 3.3 flux/global-rate plot because %s are unavailable.",
            ", ".join(missing),
        )
    else:
        out_flux_rate = PLOTS_DIR / "flux_recovery_vs_global_rate.png"
        _plot_flux_recovery_vs_global_rate(
            df=merged,
            complete_df=complete_df,
            flux_complete_col=flux_col,
            eff_complete_col=eff_col_time,
            flux_true_col=true_flux_col,
            eff_true_col=true_eff_col,
            flux_est_col=est_flux_col,
            flux_unc_abs_col=flux_unc_abs_col,
            global_rate_col=global_rate_plot_col,
            eff_plot_cols=eff_cols_for_plot,
            path=out_flux_rate,
        )

    log.info("Wrote plots in: %s", PLOTS_DIR)
    log.info("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
