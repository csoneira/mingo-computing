#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_SIMULATION/MINGO_DICTIONARY_CREATION_AND_TEST/STEPS/STEP_3_SYNTHETIC_TIME_SERIES/STEP_3_2_SYNTHETIC_TIME_SERIES/synthetic_time_series.py
Purpose: STEP 3.2 — Build synthetic dataset from basis table + complete curve.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_SIMULATION/MINGO_DICTIONARY_CREATION_AND_TEST/STEPS/STEP_3_SYNTHETIC_TIME_SERIES/STEP_3_2_SYNTHETIC_TIME_SERIES/synthetic_time_series.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import logging
from pathlib import Path
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


# ── Paths ────────────────────────────────────────────────────────────────
STEP_DIR = Path(__file__).resolve().parent
# Support both layouts:
#   - <pipeline>/STEP_3_SYNTHETIC_TIME_SERIES/STEP_3_2_SYNTHETIC_TIME_SERIES
#   - <pipeline>/STEPS/STEP_3_SYNTHETIC_TIME_SERIES/STEP_3_2_SYNTHETIC_TIME_SERIES
if STEP_DIR.parents[1].name == "STEPS":
    PIPELINE_DIR = STEP_DIR.parents[2]
else:
    PIPELINE_DIR = STEP_DIR.parents[1]
if (PIPELINE_DIR / "STEP_1_SETUP").exists() and (PIPELINE_DIR / "STEP_2_INFERENCE").exists():
    STEP_ROOT = PIPELINE_DIR
else:
    STEP_ROOT = PIPELINE_DIR / "STEPS"
SYNTHETIC_DIR = STEP_DIR.parent      # STEP_3_SYNTHETIC_TIME_SERIES
DEFAULT_CONFIG = (
    STEP_ROOT / "STEP_1_SETUP" / "STEP_1_1_COLLECT_DATA" / "INPUTS" / "config_step_1.1_method.json"
)
CONFIG_COLUMNS_PATH = (
    STEP_ROOT / "STEP_2_INFERENCE" / "STEP_2_1_ESTIMATE_PARAMS" / "INPUTS" / "config_step_2.1_columns.json"
)

DEFAULT_TIME_SERIES = (
    SYNTHETIC_DIR / "STEP_3_1_TIME_SERIES_CREATION" / "OUTPUTS" / "FILES" / "time_series.csv"
)
DEFAULT_COMPLETE_CURVE = (
    SYNTHETIC_DIR / "STEP_3_1_TIME_SERIES_CREATION" / "OUTPUTS" / "FILES" / "complete_curve_time_series.csv"
)
DEFAULT_DICTIONARY = (
    STEP_ROOT / "STEP_1_SETUP" / "STEP_1_4_ENSURE_CONTINUITY_DICTIONARY" / "OUTPUTS" / "FILES" / "dictionary.csv"
)
DEFAULT_DATASET_TEMPLATE = (
    STEP_ROOT / "STEP_1_SETUP" / "STEP_1_4_ENSURE_CONTINUITY_DICTIONARY" / "OUTPUTS" / "FILES" / "dataset.csv"
)
DEFAULT_STEP14_SELECTED_FEATURES = (
    STEP_ROOT / "STEP_1_SETUP" / "STEP_1_4_ENSURE_CONTINUITY_DICTIONARY" / "OUTPUTS" / "FILES" / "selected_feature_columns.json"
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

STEP2_INFERENCE_DIR = STEP_ROOT / "STEP_2_INFERENCE"
sys.path.insert(0, str(STEP2_INFERENCE_DIR))
try:
    from estimate_parameters import (
        _build_neighbor_weights as _step2_build_neighbor_weights,
        _local_linear_estimate as _step2_local_linear_estimate,
    )
except Exception as exc:
    raise RuntimeError(
        f"Failed to import STEP 2 inference helpers from {STEP2_INFERENCE_DIR}: {exc}"
    ) from exc

STEP12_TRANSFORM_DIR = STEP_ROOT / "STEP_1_SETUP" / "STEP_1_2_TRANSFORM_FEATURE_SPACE"
sys.path.insert(0, str(STEP12_TRANSFORM_DIR))
try:
    from transform_feature_space import (
        EFF_PLACEHOLDER_COL as STEP12_EFF_PLACEHOLDER_COL,
        EFF_PLACEHOLDER_LABEL as STEP12_EFF_PLACEHOLDER_LABEL,
        RATE_HIST_PLACEHOLDER_COL as STEP12_RATE_HIST_PLACEHOLDER_COL,
        RATE_HIST_PLACEHOLDER_LABEL as STEP12_RATE_HIST_PLACEHOLDER_LABEL,
        _resolve_feature_space_plot_suppression_patterns as _step12_resolve_feature_space_plot_suppression_patterns,
    )
except Exception as exc:
    raise RuntimeError(
        f"Failed to import STEP 1.2 plotting helpers from {STEP12_TRANSFORM_DIR}: {exc}"
    ) from exc

_FIGURE_COUNTER = 0
FIGURE_STEP_PREFIX = "3_2"


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

logging.basicConfig(
    format="[%(levelname)s] STEP_3.2 — %(message)s", level=logging.INFO, force=True
)
log = logging.getLogger("STEP_3.2")

CANONICAL_FLUX_COLUMN = "flux_cm2_min"
CANONICAL_EFF_COLUMN = "eff_sim_1"
CANONICAL_TIME_EVENTS_COLUMN = "n_events"
CANONICAL_TIME_RATE_COLUMN = "global_rate_hz_mean"
CANONICAL_TIME_RATE_FALLBACK_COLUMN = "global_rate_hz_mid"
CANONICAL_TIME_DURATION_COLUMN = "duration_seconds"
CANONICAL_DENSITY_EXPONENT = 1.0
CANONICAL_DENSITY_CLIP_MIN = 0.25
CANONICAL_DENSITY_CLIP_MAX = 4.0
CANONICAL_TT_RATE_CONSISTENCY_BLEND = 0.0
CANONICAL_HIST_RATE_MEAN_CONSISTENCY_BLEND = 0.0

TT_RATE_COLUMN_RE = re.compile(r"^(?P<prefix>[A-Za-z0-9]+)_tt_(?P<trigger>[0-9]+)_rate_hz$")
HIST_RATE_COLUMN_RE = re.compile(r"^events_per_second_(?P<bin>\d+)_rate_hz$")
EFF_VECTOR_COL_RE = re.compile(
    r"^efficiency_vector_p(?P<plane>[1-4])_(?P<axis>x|y|theta)_bin_(?P<bin>\d+)_eff$"
)


STEP32_WEIGHTING_KEYS = {
    "basis_source",
    "basis_n_events_column",
    "basis_parameter_set_column",
    "parameter_space_columns",
    "basis_n_events_tolerance_pct",
    "basis_n_events_tolerance",
    "basis_min_rows",
    "basis_event_filter_mode",
    "weighting_method",
    "interpolation_aggregation",
    "distance_hardness",
    "density_correction_enabled",
    "density_correction_k_neighbors",
    "enforce_distance_monotonic_weights",
    "top_k",
    "random_seed",
    "highlight_point_index",
}

STEP32_WEIGHTING_LEGACY_IGNORED_KEYS = {
    "flux_column",
    "eff_column",
    "time_n_events_column",
    "time_rate_column",
    "time_duration_column",
    "distance_sigma_flux_fraction",
    "distance_sigma_eff_fraction",
    "distance_sigma_flux_abs",
    "distance_sigma_eff_abs",
    "density_correction_space",
    "density_correction_exponent",
    "density_correction_clip_min",
    "density_correction_clip_max",
}

STEP32_WEIGHTING_DEFAULTS = {
    "basis_source": "auto",
    "basis_n_events_column": "n_events",
    "basis_parameter_set_column": "param_hash_x",
    "parameter_space_columns": None,
    "basis_n_events_tolerance_pct": 25,
    "basis_min_rows": 1,
    "basis_event_filter_mode": "event_tolerance",
    "weighting_method": "inverse_distance",
    "interpolation_aggregation": "local_linear",
    "distance_hardness": 2.0,
    "density_correction_enabled": False,
    "density_correction_k_neighbors": None,
    "enforce_distance_monotonic_weights": False,
    "top_k": None,
    "random_seed": None,
    "highlight_point_index": None,
}


def _normalize_weighting_method(value: object) -> str:
    text = str(value).strip().lower() if value is not None else ""
    if text in {"closest_point", "closest-point", "take_closest_point", "take-closest-point"}:
        return "closest_point"
    if text in {"nearest", "nn", "1nn"}:
        return "nearest"
    if text in {"inverse_distance", "idw", "inverse", "invdist"}:
        return "inverse_distance"
    if text == "softmax":
        return "softmax"
    return "gaussian"


def _normalize_basis_source(value: object) -> str:
    text = str(value).strip().lower() if value is not None else ""
    if text in {"", "auto", "default"}:
        return "auto"
    if text in {"dataset", "data", "template"}:
        return "dataset"
    if text in {"dictionary", "dict"}:
        return "dictionary"
    return text


def _resolve_basis_source(value: object, *, weighting_method: str) -> tuple[str, bool]:
    normalized = _normalize_basis_source(value)
    if normalized == "auto":
        return ("dataset" if weighting_method == "closest_point" else "dictionary"), True
    return normalized, False


def _normalize_step31_curve_data_mode(value: object) -> str:
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


def _resolve_step31_curve_data_mode(time_df: pd.DataFrame) -> tuple[str, bool]:
    if "step31_curve_data_mode" not in time_df.columns:
        return "synthetic_data_curve", False
    raw = pd.Series(time_df["step31_curve_data_mode"], index=time_df.index).dropna().astype(str).str.strip()
    if raw.empty:
        return "synthetic_data_curve", False
    modes = sorted({_normalize_step31_curve_data_mode(v) for v in raw.tolist() if str(v).strip()})
    if not modes:
        return "synthetic_data_curve", False
    if len(modes) > 1:
        raise ValueError(f"STEP 3.1 curve data mode is inconsistent across rows: {modes}")
    return modes[0], True


def _normalize_basis_event_filter_mode(value: object) -> str:
    text = str(value).strip().lower().replace(" ", "_").replace("-", "_") if value is not None else ""
    if text in {"", "default", "event_tolerance", "tolerance", "strict"}:
        return "event_tolerance"
    if text in {"ignore_events", "disabled", "off", "none", "all_rows"}:
        return "ignore_events"
    if text in {
        "tolerance_then_param_nearest",
        "param_nearest_fallback",
        "closest_n_fallback",
        "nearest_n_fallback",
        "pad_param_nearest",
    }:
        return "tolerance_then_param_nearest"
    return "event_tolerance"


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

def _merge_weighting_cfg_from_step13(cfg_32: dict, cfg_13: dict) -> tuple[dict, list[str]]:
    """Build STEP 3.2 config with weighting sourced only from STEP 1.3 block.

    - Keep non-weighting keys from `step_3_2` (mainly path overrides).
    - Fill weighting keys from internal defaults.
    - Apply centralized weighting keys from `step_1_3.weighting_shared`.
      Fallback: `step_1_3.step_3_2_weighting` (deprecated alias).
    - Apply optional backward-compatibility overrides from `step_1_3.weighting_overrides`.
    """
    raw_cfg_32 = dict(cfg_32)
    ignored_step32_weighting_keys = sorted(
        key for key in raw_cfg_32.keys() if key in STEP32_WEIGHTING_KEYS
    )
    if ignored_step32_weighting_keys:
        log.info(
            "Ignoring %d weighting key(s) from step_3_2; using step_1_3.weighting_shared + internal defaults.",
            len(ignored_step32_weighting_keys),
        )
    for legacy_key in STEP32_WEIGHTING_LEGACY_IGNORED_KEYS:
        if raw_cfg_32.get(legacy_key) is not None:
            log.warning(
                "Deprecated key step_3_2.%s detected; ignored. Using fixed canonical settings.",
                legacy_key,
            )

    merged = {
        key: value
        for key, value in raw_cfg_32.items()
        if key not in STEP32_WEIGHTING_KEYS and key not in STEP32_WEIGHTING_LEGACY_IGNORED_KEYS
    }
    merged.update(STEP32_WEIGHTING_DEFAULTS)
    applied_keys: set[str] = set()

    legacy_central_weighting = cfg_13.get("step_3_2_weighting", {})
    if isinstance(legacy_central_weighting, dict):
        if legacy_central_weighting and not isinstance(cfg_13.get("weighting_shared"), dict):
            log.info(
                "Using deprecated key step_1_3.step_3_2_weighting; prefer step_1_3.weighting_shared."
            )
        for legacy_key in STEP32_WEIGHTING_LEGACY_IGNORED_KEYS:
            if legacy_central_weighting.get(legacy_key) is not None:
                log.warning(
                    "Deprecated key step_1_3.step_3_2_weighting.%s detected; ignored. "
                    "Using fixed canonical settings.",
                    legacy_key,
                )
        for key in STEP32_WEIGHTING_KEYS:
            if key in legacy_central_weighting and legacy_central_weighting.get(key) is not None:
                merged[key] = legacy_central_weighting[key]
                applied_keys.add(key)

    # Warn when deprecated and current keys conflict
    central_check = cfg_13.get("weighting_shared", {})
    if isinstance(legacy_central_weighting, dict) and isinstance(central_check, dict):
        for key in STEP32_WEIGHTING_KEYS:
            lv, cv = legacy_central_weighting.get(key), central_check.get(key)
            if lv is not None and cv is not None and lv != cv:
                log.warning(
                    "Config conflict: step_1_3.step_3_2_weighting.%s=%r vs "
                    "step_1_3.weighting_shared.%s=%r; using weighting_shared.",
                    key, lv, key, cv,
                )

    central_weighting = cfg_13.get("weighting_shared", {})
    if isinstance(central_weighting, dict):
        for legacy_key in STEP32_WEIGHTING_LEGACY_IGNORED_KEYS:
            if central_weighting.get(legacy_key) is not None:
                log.warning(
                    "Deprecated key step_1_3.weighting_shared.%s detected; ignored. "
                    "Using fixed canonical settings.",
                    legacy_key,
                )
        for key in STEP32_WEIGHTING_KEYS:
            if key in central_weighting and central_weighting.get(key) is not None:
                merged[key] = central_weighting[key]
                applied_keys.add(key)

    # Backward-compatible alias already used by STEP 1.3 itself.
    legacy_overrides = cfg_13.get("weighting_overrides", {})
    if isinstance(legacy_overrides, dict):
        for legacy_key in STEP32_WEIGHTING_LEGACY_IGNORED_KEYS:
            if legacy_overrides.get(legacy_key) is not None:
                log.warning(
                    "Deprecated key step_1_3.weighting_overrides.%s detected; ignored. "
                    "Using fixed canonical settings.",
                    legacy_key,
                )
        for key in STEP32_WEIGHTING_KEYS:
            if key in legacy_overrides and legacy_overrides.get(key) is not None:
                merged[key] = legacy_overrides[key]
                applied_keys.add(key)

    return merged, sorted(applied_keys)


def _safe_float(value: object, default: float) -> float:
    """Convert to float with fallback."""
    try:
        out = float(value)
    except (TypeError, ValueError):
        return float(default)
    if np.isfinite(out):
        return out
    return float(default)


def _safe_int(value: object, default: int, minimum: int | None = None) -> int:
    """Convert to int with fallback and optional lower bound."""
    try:
        out = int(value)
    except (TypeError, ValueError):
        out = int(default)
    if minimum is not None:
        out = max(int(minimum), out)
    return out


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
    """Return efficiency column from table, with fallback candidates."""
    if preferred in df.columns:
        return preferred
    for candidate in (
        "eff_sim_1", "eff_sim_2", "eff_sim_3", "eff_sim_4",
        "eff_empirical_1", "eff_empirical_2", "eff_empirical_3", "eff_empirical_4",
    ):
        if candidate in df.columns:
            return candidate
    raise KeyError("No efficiency column found in table.")


def _choose_common_eff_column(
    time_df: pd.DataFrame,
    basis_df: pd.DataFrame,
    preferred: str,
) -> str:
    """Resolve one efficiency column present in both time targets and basis."""
    ordered = [preferred]
    ordered.extend([
        "eff_sim_1", "eff_sim_2", "eff_sim_3", "eff_sim_4",
        "eff_empirical_1", "eff_empirical_2", "eff_empirical_3", "eff_empirical_4",
        "eff",
    ])
    seen: set[str] = set()
    for candidate in ordered:
        name = str(candidate).strip()
        if not name or name in seen:
            continue
        seen.add(name)
        if name in time_df.columns and name in basis_df.columns:
            return name
    raise KeyError(
        "No common efficiency column found between time series and basis "
        f"(preferred={preferred!r})."
    )


def _optional_common_column(
    time_df: pd.DataFrame,
    basis_df: pd.DataFrame,
    preferred: str,
) -> str | None:
    name = str(preferred).strip()
    if not name:
        return None
    if name in time_df.columns and name in basis_df.columns:
        return name
    return None


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


def _resolve_parameter_space_columns(
    time_df: pd.DataFrame,
    basis_df: pd.DataFrame,
    preferred_eff: str | None = None,
) -> list[str]:
    """Return ordered parameter-space dimensions shared by target and basis tables."""
    common = set(time_df.columns) & set(basis_df.columns)
    ordered: list[str] = []

    if "flux_cm2_min" in common:
        ordered.append("flux_cm2_min")
    if "cos_n" in common:
        ordered.append("cos_n")

    eff_priority = [
        "eff_sim_1", "eff_sim_2", "eff_sim_3", "eff_sim_4",
        "eff_empirical_1", "eff_empirical_2", "eff_empirical_3", "eff_empirical_4",
    ]
    if preferred_eff is not None:
        pe = str(preferred_eff).strip()
        if pe in common and pe not in eff_priority:
            eff_priority = [pe] + eff_priority
        elif pe in common:
            eff_priority = [pe] + [c for c in eff_priority if c != pe]
    for col in eff_priority:
        if col in common and col not in ordered:
            ordered.append(col)

    for col in sorted(common):
        if col in ordered:
            continue
        if _is_parameter_space_column(col):
            ordered.append(col)
    return ordered


def _parse_column_spec(value: object) -> list[str]:
    """Parse list-like config values accepting arrays or comma-separated text."""
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        if not text or text.lower() == "auto":
            return []
        if text.startswith("[") and text.endswith("]"):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    return [str(x).strip() for x in parsed if str(x).strip()]
            except json.JSONDecodeError:
                pass
        return [part.strip() for part in text.split(",") if part.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(x).strip() for x in value if str(x).strip()]
    text = str(value).strip()
    return [text] if text and text.lower() != "auto" else []


def _resolve_parameter_space_columns_from_cfg(
    *,
    time_df: pd.DataFrame,
    basis_df: pd.DataFrame,
    preferred_eff: str | None = None,
    configured_columns: object = None,
) -> list[str]:
    """Resolve parameter-space columns from config or fallback auto detection."""
    requested = _parse_column_spec(configured_columns)
    if not requested:
        return _resolve_parameter_space_columns(
            time_df=time_df,
            basis_df=basis_df,
            preferred_eff=preferred_eff,
        )

    common = set(time_df.columns) & set(basis_df.columns)
    resolved: list[str] = []
    missing: list[str] = []
    for col in requested:
        if col in common and col not in resolved:
            resolved.append(col)
        elif col not in common:
            missing.append(col)

    if missing:
        log.warning(
            "Ignoring configured parameter-space columns not present in both tables: %s",
            missing,
        )
    if not resolved:
        raise KeyError("No configured parameter-space columns available in both time and basis tables.")
    return resolved


def _prepare_standardized_param_space(
    dict_param_matrix: np.ndarray,
    target_param_matrix: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Scale parameter dimensions by dictionary min-max span for isotropic distances."""
    X = np.asarray(dict_param_matrix, dtype=float)
    Y = np.asarray(target_param_matrix, dtype=float)
    if X.ndim != 2 or Y.ndim != 2:
        raise ValueError("Parameter matrices must be 2D.")
    if X.shape[1] != Y.shape[1]:
        raise ValueError("Dictionary and target parameter matrices must share n_dims.")

    mins = np.nanmin(X, axis=0)
    maxs = np.nanmax(X, axis=0)
    spans = maxs - mins
    spans = np.where(np.isfinite(spans) & (spans > 1e-12), spans, 1.0)
    Xs = (X - mins[np.newaxis, :]) / spans[np.newaxis, :]
    Ys = (Y - mins[np.newaxis, :]) / spans[np.newaxis, :]
    return Xs, Ys, spans


def _pairwise_standardized_squared_distances(
    dict_param_matrix: np.ndarray,
    target_param_matrix: np.ndarray,
) -> np.ndarray:
    """Pairwise squared Euclidean distances in standardized parameter space."""
    Xs, Ys, _ = _prepare_standardized_param_space(dict_param_matrix, target_param_matrix)
    x2 = np.sum(Xs * Xs, axis=1, dtype=float)
    y2 = np.sum(Ys * Ys, axis=1, dtype=float)
    d2 = y2[:, None] + x2[None, :] - 2.0 * (Ys @ Xs.T)
    return np.maximum(d2, 0.0)


def _build_event_mask(
    basis_events: np.ndarray | None,
    target_events: np.ndarray | None,
    *,
    tolerance_pct: float,
    min_rows: int,
    filter_mode: str = "event_tolerance",
    basis_param_matrix: np.ndarray | None = None,
    target_param_matrix: np.ndarray | None = None,
) -> tuple[np.ndarray | None, dict]:
    """Build per-target basis mask from event-count proximity."""
    mode = _normalize_basis_event_filter_mode(filter_mode)
    info = {
        "mode": "disabled",
        "filter_mode": mode,
        "tolerance_pct": float(tolerance_pct),
        "min_rows_fallback": int(max(1, int(min_rows))),
    }
    if mode == "ignore_events":
        info["mode"] = "disabled_by_config"
        return None, info
    if basis_events is None or target_events is None:
        return None, info

    b = np.asarray(basis_events, dtype=float)
    t = np.asarray(target_events, dtype=float)
    n_targets = len(t)
    n_basis = len(b)
    if n_targets == 0 or n_basis == 0:
        return None, info

    finite_basis = np.isfinite(b)
    finite_targets = np.isfinite(t)
    info["n_basis_rows"] = int(n_basis)
    info["n_basis_rows_with_finite_events"] = int(np.sum(finite_basis))
    info["n_targets"] = int(n_targets)
    info["n_targets_with_finite_events"] = int(np.sum(finite_targets))
    if not np.any(finite_basis):
        info["mode"] = "disabled_no_finite_basis_events"
        return None, info

    tol_pct = max(float(tolerance_pct), 0.0)
    keep_n = max(1, int(min_rows))
    mask = np.zeros((n_targets, n_basis), dtype=bool)
    counts = np.zeros(n_targets, dtype=int)
    fallback_points = 0
    param_nearest_padding_points = 0
    finite_idx = np.where(finite_basis)[0]
    finite_param_rows: np.ndarray | None = None
    finite_target_params: np.ndarray | None = None
    basis_params_std: np.ndarray | None = None
    target_params_std: np.ndarray | None = None
    if (
        mode == "tolerance_then_param_nearest"
        and basis_param_matrix is not None
        and target_param_matrix is not None
    ):
        basis_params_std, target_params_std, _ = _prepare_standardized_param_space(
            dict_param_matrix=np.asarray(basis_param_matrix, dtype=float),
            target_param_matrix=np.asarray(target_param_matrix, dtype=float),
        )
        finite_param_rows = np.all(np.isfinite(basis_params_std), axis=1)
        finite_target_params = np.all(np.isfinite(target_params_std), axis=1)

    for i in range(n_targets):
        if not finite_targets[i]:
            m = finite_basis.copy()
        else:
            tol_abs = abs(float(t[i])) * tol_pct / 100.0
            m = finite_basis & (np.abs(b - float(t[i])) <= tol_abs)
            if not np.any(m):
                take = min(keep_n, len(finite_idx))
                nearest = finite_idx[np.argsort(np.abs(b[finite_idx] - float(t[i])))[:take]]
                m = np.zeros(n_basis, dtype=bool)
                m[nearest] = True
                fallback_points += 1
        if (
            mode == "tolerance_then_param_nearest"
            and int(np.sum(m)) < keep_n
            and finite_param_rows is not None
            and finite_target_params is not None
            and basis_params_std is not None
            and target_params_std is not None
            and bool(finite_target_params[i])
        ):
            candidates = np.flatnonzero(finite_param_rows & ~m)
            if candidates.size:
                d = np.sum((basis_params_std[candidates] - target_params_std[i][None, :]) ** 2, axis=1)
                take = min(keep_n - int(np.sum(m)), candidates.size)
                nearest = candidates[np.argsort(d)[:take]]
                m[nearest] = True
                param_nearest_padding_points += 1
        mask[i] = m
        counts[i] = int(np.sum(m))

    info["mode"] = "enabled"
    info["fallback_points_count"] = int(fallback_points)
    info["param_nearest_padding_points_count"] = int(param_nearest_padding_points)
    info["allowed_rows_per_target_min"] = int(np.min(counts))
    info["allowed_rows_per_target_median"] = float(np.median(counts))
    info["allowed_rows_per_target_max"] = int(np.max(counts))
    return mask, info


def _resolve_step31_dataset_curve_basis_positions(
    *,
    time_df: pd.DataFrame,
    basis_df: pd.DataFrame,
    valid_basis_mask: np.ndarray,
) -> np.ndarray:
    n_targets = len(time_df)
    valid_positions = np.flatnonzero(np.asarray(valid_basis_mask, dtype=bool))
    pos_by_row_index = {int(src_idx): int(pos) for pos, src_idx in enumerate(valid_positions.tolist())}

    row_index_series = pd.to_numeric(time_df.get("step31_source_row_index"), errors="coerce")
    filename_series = pd.Series(time_df.get("step31_source_filename_base"), index=time_df.index)

    basis_filename_to_pos: dict[str, int] = {}
    if "filename_base" in basis_df.columns:
        basis_filename = basis_df.loc[valid_positions, "filename_base"].astype(str).fillna("")
        for pos, text in enumerate(basis_filename.tolist()):
            if text and text not in basis_filename_to_pos:
                basis_filename_to_pos[text] = int(pos)

    out = np.full(n_targets, -1, dtype=int)
    missing_rows: list[int] = []
    for i in range(n_targets):
        pos = -1
        row_value = row_index_series.iloc[i] if i < len(row_index_series) else np.nan
        if np.isfinite(row_value):
            pos = int(pos_by_row_index.get(int(row_value), -1))
        if pos < 0 and i < len(filename_series):
            name = str(filename_series.iloc[i]).strip()
            if name:
                pos = int(basis_filename_to_pos.get(name, -1))
        if pos < 0:
            missing_rows.append(i)
        out[i] = pos

    if missing_rows:
        preview = ", ".join(str(i) for i in missing_rows[:8])
        raise ValueError(
            "STEP 3.1 dataset_data_curve rows could not be resolved in STEP 3.2 basis "
            f"(missing {len(missing_rows)} row(s), first indices: {preview})."
        )
    return out


def _select_parameter_set_column(df: pd.DataFrame, configured: str | None) -> str | None:
    """Resolve parameter-set identifier column for basis deduplication."""
    if configured is not None:
        col = str(configured).strip()
        if col and col in df.columns:
            return col
    for col in ("param_hash_x", "param_hash_y", "param_set_id"):
        if col in df.columns:
            return col
    return None


def _resolve_basis_events_column(
    basis_df: pd.DataFrame,
    configured: str | None,
) -> tuple[str | None, str]:
    """Resolve event-count column on basis table with robust fallbacks."""
    requested = str(configured).strip() if configured is not None else ""

    def _is_usable(col: str) -> bool:
        if col not in basis_df.columns:
            return False
        vals = pd.to_numeric(basis_df[col], errors="coerce")
        return bool(vals.notna().any())

    if requested and _is_usable(requested):
        return requested, "configured"

    fallback_candidates = [
        "n_events",
        "selected_rows",
        "requested_rows",
        "generated_events_count",
    ]
    for col in fallback_candidates:
        if _is_usable(col):
            return col, "fallback"

    if requested and requested in basis_df.columns:
        return requested, "configured_non_numeric"
    return None, "missing"


def _build_one_per_parameter_set_mask(
    *,
    parameter_set_values: np.ndarray,
    basis_events: np.ndarray | None,
    target_events: np.ndarray | None,
    basis_param_matrix: np.ndarray,
    target_param_matrix: np.ndarray,
) -> tuple[np.ndarray, dict]:
    """Select exactly one basis row per parameter set and target point."""
    group_vals = np.asarray(parameter_set_values, dtype=object)
    n_basis = len(group_vals)
    basis_params = np.asarray(basis_param_matrix, dtype=float)
    target_params = np.asarray(target_param_matrix, dtype=float)
    if basis_params.ndim != 2 or target_params.ndim != 2:
        raise ValueError("basis_param_matrix and target_param_matrix must be 2D.")
    if basis_params.shape[0] != n_basis:
        raise ValueError("basis_param_matrix row count must match parameter_set_values length.")
    if basis_params.shape[1] != target_params.shape[1]:
        raise ValueError("Basis/target parameter matrices must share n_dims.")
    n_targets = int(target_params.shape[0])
    if n_basis == 0 or n_targets == 0:
        return np.zeros((n_targets, n_basis), dtype=bool), {
            "mode": "empty",
            "n_parameter_sets": 0,
            "allowed_rows_per_target_min": 0,
            "allowed_rows_per_target_median": 0.0,
            "allowed_rows_per_target_max": 0,
        }

    # Standardize dimensions once so nearest decisions are isotropic
    # across all parameter-space coordinates.
    basis_params_std, target_params_std, _ = _prepare_standardized_param_space(
        dict_param_matrix=basis_params,
        target_param_matrix=target_params,
    )

    # Stable per-group indices preserving first-seen group order.
    groups: dict[object, list[int]] = {}
    for j, g in enumerate(group_vals):
        groups.setdefault(g, []).append(j)
    group_index_arrays = [np.asarray(idxs, dtype=int) for idxs in groups.values()]

    be = None if basis_events is None else np.asarray(basis_events, dtype=float)
    te = None if target_events is None else np.asarray(target_events, dtype=float)

    mask = np.zeros((n_targets, n_basis), dtype=bool)
    for i in range(n_targets):
        t_ev = np.nan if te is None or i >= len(te) else float(te[i])
        t_vec = target_params_std[i]

        for idxs in group_index_arrays:
            chosen = int(idxs[0])
            if be is not None:
                ev = be[idxs]
                finite = np.isfinite(ev)
                if np.any(finite) and np.isfinite(t_ev):
                    cand = idxs[finite]
                    dev = np.abs(be[cand] - t_ev)
                    best = np.flatnonzero(dev == np.min(dev))
                    cand_best = cand[best]
                    if len(cand_best) > 1:
                        d = np.sum((basis_params_std[cand_best] - t_vec[np.newaxis, :]) ** 2, axis=1)
                        chosen = int(cand_best[int(np.argmin(d))])
                    else:
                        chosen = int(cand_best[0])
                elif np.any(finite):
                    cand = idxs[finite]
                    d = np.sum((basis_params_std[cand] - t_vec[np.newaxis, :]) ** 2, axis=1)
                    chosen = int(cand[int(np.argmin(d))])
                else:
                    d = np.sum((basis_params_std[idxs] - t_vec[np.newaxis, :]) ** 2, axis=1)
                    chosen = int(idxs[int(np.argmin(d))])
            else:
                d = np.sum((basis_params_std[idxs] - t_vec[np.newaxis, :]) ** 2, axis=1)
                chosen = int(idxs[int(np.argmin(d))])
            mask[i, chosen] = True

    counts = np.sum(mask, axis=1)
    info = {
        "mode": "one_row_per_parameter_set",
        "n_parameter_sets": int(len(group_index_arrays)),
        "parameter_space_dims": int(basis_params.shape[1]),
        "allowed_rows_per_target_min": int(np.min(counts)) if len(counts) else 0,
        "allowed_rows_per_target_median": float(np.median(counts)) if len(counts) else 0.0,
        "allowed_rows_per_target_max": int(np.max(counts)) if len(counts) else 0,
    }
    if be is not None:
        info["basis_rows_with_finite_events"] = int(np.sum(np.isfinite(be)))
    return mask, info


def _build_linear_distance_center_weights(
    basis_flux: np.ndarray,
    basis_eff: np.ndarray,
    target_flux: np.ndarray,
    target_eff: np.ndarray,
    *,
    event_mask: np.ndarray | None,
    top_k: int | None,
    hardness: float = 1.0,
) -> np.ndarray:
    """Build linear distance-based weights for center estimation in (flux, eff)."""
    bf = np.asarray(basis_flux, dtype=float)
    be = np.asarray(basis_eff, dtype=float)
    tf = np.asarray(target_flux, dtype=float)
    te = np.asarray(target_eff, dtype=float)
    if bf.ndim != 1 or be.ndim != 1 or len(bf) != len(be):
        raise ValueError("basis_flux and basis_eff must be 1D with same length")
    if tf.ndim != 1 or te.ndim != 1 or len(tf) != len(te):
        raise ValueError("target_flux and target_eff must be 1D with same length")

    flux_span = max(float(np.nanmax(bf) - np.nanmin(bf)), 1e-12)
    eff_span = max(float(np.nanmax(be) - np.nanmin(be)), 1e-12)
    dx = (tf[:, None] - bf[None, :]) / flux_span
    dy = (te[:, None] - be[None, :]) / eff_span
    d_full = np.sqrt(dx * dx + dy * dy)
    d = d_full.copy()

    n_targets, n_basis = d.shape
    if event_mask is not None:
        m = np.asarray(event_mask, dtype=bool)
        if m.shape != d.shape:
            raise ValueError("event_mask shape must match (n_targets, n_basis)")
        d = np.where(m, d, np.inf)

    k = None
    if top_k is not None:
        k = max(1, int(top_k))

    hard = max(float(hardness), 1e-6)
    w = np.zeros_like(d, dtype=float)
    for i in range(n_targets):
        row = d[i]
        finite_idx = np.where(np.isfinite(row))[0]
        if finite_idx.size == 0:
            # Fallback: nearest overall in flux-eff space.
            j = int(np.argmin(d_full[i]))
            w[i, j] = 1.0
            continue

        selected_idx = finite_idx
        if k is not None and k < finite_idx.size:
            order = finite_idx[np.argsort(row[finite_idx])]
            selected_idx = order[:k]

        sel_d = row[selected_idx]
        dmin = float(np.min(sel_d))
        dmax = float(np.max(sel_d))
        if dmax <= dmin + 1e-12:
            w[i, selected_idx] = 1.0 / float(len(selected_idx))
            continue

        # Linear profile: closest gets highest weight, farthest gets zero.
        lin = 1.0 - ((sel_d - dmin) / (dmax - dmin))
        lin = np.clip(lin, 0.0, None)
        if hard != 1.0:
            lin = np.power(lin, hard)
        s = float(np.sum(lin))
        if s <= 0.0:
            w[i, selected_idx] = 1.0 / float(len(selected_idx))
        else:
            w[i, selected_idx] = lin / s
    return w


def _compute_inverse_density_scaling(
    basis_param_matrix: np.ndarray,
    *,
    k_neighbors: int,
    exponent: float,
    clip_min: float,
    clip_max: float,
) -> tuple[np.ndarray, dict]:
    """Compute per-basis scaling to reduce dense-region dominance."""
    basis = np.asarray(basis_param_matrix, dtype=float)
    if basis.ndim != 2:
        raise ValueError("basis_param_matrix must be 2D.")
    n = int(basis.shape[0])
    info = {
        "enabled": True,
        "k_neighbors": int(k_neighbors),
        "exponent": float(exponent),
        "clip_min": float(clip_min),
        "clip_max": float(clip_max),
        "n_basis": int(n),
        "n_dims": int(basis.shape[1]) if basis.ndim == 2 else 0,
    }
    if n == 0:
        return np.array([], dtype=float), info
    if n == 1:
        return np.ones(1, dtype=float), info

    coords, _, _ = _prepare_standardized_param_space(
        dict_param_matrix=basis,
        target_param_matrix=basis,
    )

    k = max(1, int(k_neighbors))
    k_eff = min(k, n - 1)
    kth = np.empty(n, dtype=float)

    # Chunk pairwise distances to limit peak memory at large n_basis.
    chunk_size = 512
    for s in range(0, n, chunk_size):
        e = min(n, s + chunk_size)
        diff = coords[s:e, None, :] - coords[None, :, :]
        d2 = np.sum(diff * diff, axis=2)
        row_idx = np.arange(e - s)
        col_idx = np.arange(s, e)
        d2[row_idx, col_idx] = np.inf
        kth[s:e] = np.sqrt(np.partition(d2, k_eff - 1, axis=1)[:, k_eff - 1])

    exp = max(float(exponent), 0.0)
    scale = np.power(np.clip(kth, 1e-12, None), exp)
    med = float(np.median(scale[np.isfinite(scale)])) if np.isfinite(scale).any() else 1.0
    if med <= 0.0 or not np.isfinite(med):
        med = 1.0
    scale = scale / med

    lo = max(float(clip_min), 1e-6)
    hi = max(float(clip_max), lo)
    scale = np.clip(scale, lo, hi)

    info["effective_k_neighbors"] = int(k_eff)
    info["scale_min"] = float(np.min(scale))
    info["scale_median"] = float(np.median(scale))
    info["scale_max"] = float(np.max(scale))
    return scale, info


def _build_weights(
    dict_param_matrix: np.ndarray,
    target_param_matrix: np.ndarray,
    *,
    method: str,
    top_k: int | None,
    distance_hardness: float = 1.0,
    density_scaling: np.ndarray | None = None,
    event_mask: np.ndarray | None = None,
    enforce_distance_monotonic_weights: bool = False,
) -> np.ndarray:
    """Compute normalized basis weights for each target point."""
    d2 = _pairwise_standardized_squared_distances(
        dict_param_matrix=np.asarray(dict_param_matrix, dtype=float),
        target_param_matrix=np.asarray(target_param_matrix, dtype=float),
    )
    if event_mask is not None and event_mask.shape != d2.shape:
        raise ValueError("event_mask shape must match (n_targets, n_basis)")

    method_key = _normalize_weighting_method(method)
    if method_key in {"nearest", "closest_point"}:
        w = np.zeros_like(d2, dtype=float)
        for i in range(d2.shape[0]):
            row_d2 = d2[i]
            if event_mask is not None:
                row_mask = event_mask[i]
                if np.any(row_mask):
                    row_d2 = np.where(row_mask, row_d2, np.inf)
            j = int(np.argmin(row_d2))
            w[i, j] = 1.0
        return w

    if method_key in {"inverse_distance", "softmax"}:
        distances = np.sqrt(np.maximum(d2, 0.0))
        w = np.zeros_like(distances, dtype=float)
        k = None if top_k is None else max(1, int(top_k))
        idw_power = max(float(distance_hardness), 0.0)
        for i in range(distances.shape[0]):
            row_d = distances[i]
            finite = np.isfinite(row_d)
            if event_mask is not None:
                finite &= np.asarray(event_mask[i], dtype=bool)
            idx = np.where(finite)[0]
            if idx.size == 0:
                j = int(np.argmin(row_d))
                w[i, j] = 1.0
                continue
            if k is not None and k < idx.size:
                idx = idx[np.argsort(row_d[idx], kind="mergesort")[:k]]
            row_weights = _step2_build_neighbor_weights(
                row_d[idx],
                weighting_mode=method_key,
                idw_power=idw_power,
                softmax_temperature=1.0,
                distance_floor=1e-12,
            )
            if np.sum(row_weights) <= 0.0:
                j = int(idx[np.argmin(row_d[idx])])
                w[i, j] = 1.0
            else:
                w[i, idx] = row_weights
        return w

    # Legacy gaussian mode
    hard = max(float(distance_hardness), 1e-6)
    w = np.exp(-0.5 * hard * d2)
    if event_mask is not None:
        w = np.where(event_mask, w, 0.0)
    if density_scaling is not None:
        ds = np.asarray(density_scaling, dtype=float)
        if ds.ndim != 1 or ds.shape[0] != w.shape[1]:
            raise ValueError("density_scaling must be 1D with length n_basis")
        w = w * ds[None, :]

    k = None
    if top_k is not None:
        k = max(1, int(top_k))
    if k is not None and k < w.shape[1]:
        keep = np.zeros_like(w, dtype=bool)
        idx_part = np.argpartition(w, -k, axis=1)[:, -k:]
        rows = np.arange(w.shape[0])[:, None]
        keep[rows, idx_part] = True
        w = np.where(keep, w, 0.0)

    if enforce_distance_monotonic_weights:
        # Ensure distance ordering is reflected in final contributions:
        # for each target row, farther selected candidates cannot exceed
        # closer candidates in pre-normalization weight.
        for i in range(w.shape[0]):
            pos = w[i] > 0.0
            if not np.any(pos):
                continue
            idx = np.where(pos & np.isfinite(d2[i]))[0]
            if idx.size < 2:
                continue
            idx = idx[np.argsort(d2[i, idx])]
            prev = float(w[i, idx[0]])
            for j in idx[1:]:
                cur = float(w[i, j])
                if cur > prev:
                    w[i, j] = prev
                    cur = prev
                prev = cur

    # Row-wise normalization with nearest fallback on empty rows.
    row_sum = w.sum(axis=1, keepdims=True)
    empty = (row_sum[:, 0] <= 0.0)
    if np.any(empty):
        for i in np.where(empty)[0]:
            row_d2 = d2[i]
            if event_mask is not None:
                row_mask = event_mask[i]
                if np.any(row_mask):
                    row_d2 = np.where(row_mask, row_d2, np.inf)
            j = int(np.argmin(row_d2))
            w[i] = 0.0
            w[i, j] = 1.0
        row_sum = w.sum(axis=1, keepdims=True)
    return w / row_sum


def _normalize_interpolation_aggregation(value: object) -> str:
    text = str(value).strip().lower() if value is not None else ""
    if text in {"local_linear", "local-linear", "local_linear_ridge", "llr"}:
        return "local_linear"
    return "weighted_mean"


def _weighted_mean_1d(values: np.ndarray, weights_row: np.ndarray) -> float:
    vals = np.asarray(values, dtype=float)
    w = np.asarray(weights_row, dtype=float)
    mask = np.isfinite(vals) & np.isfinite(w) & (w > 0.0)
    if not np.any(mask):
        return np.nan
    vals = vals[mask]
    w = w[mask]
    den = float(np.sum(w))
    if den <= 0.0 or not np.isfinite(den):
        return np.nan
    return float(np.sum(w * vals) / den)


def _local_linear_predict(
    values: np.ndarray,
    weights_row: np.ndarray,
    basis_params_std: np.ndarray,
    target_param_std: np.ndarray,
    *,
    column_name: str | None = None,
    ridge_lambda: float = 1e-2,
) -> float:
    vals = np.asarray(values, dtype=float)
    w = np.asarray(weights_row, dtype=float)
    X = np.asarray(basis_params_std, dtype=float)
    x0 = np.asarray(target_param_std, dtype=float)
    fallback = _weighted_mean_1d(vals, w)
    if X.ndim != 2 or vals.ndim != 1 or w.ndim != 1:
        return fallback
    if X.shape[0] != vals.size or vals.size != w.size:
        return fallback
    if X.shape[1] != x0.size:
        return fallback

    pred = _step2_local_linear_estimate(
        values=vals,
        weights=w,
        sample_features=x0,
        neighbor_features=X,
        parameter_name=column_name,
        ridge_lambda=ridge_lambda,
    )
    if np.isfinite(pred):
        return float(pred)
    return fallback


def _weighted_numeric_columns(
    weights: np.ndarray,
    dict_df: pd.DataFrame,
    columns: list[str],
    *,
    interpolation_aggregation: str = "weighted_mean",
    basis_param_matrix: np.ndarray | None = None,
    target_param_matrix: np.ndarray | None = None,
) -> dict[str, np.ndarray]:
    """Interpolate numeric dictionary columns, NaN-aware."""
    out: dict[str, np.ndarray] = {}
    n_rows = weights.shape[0]
    agg_mode = _normalize_interpolation_aggregation(interpolation_aggregation)
    use_local_linear = (
        agg_mode == "local_linear"
        and basis_param_matrix is not None
        and target_param_matrix is not None
    )
    basis_std = None
    target_std = None
    if use_local_linear:
        basis_std, target_std, _ = _prepare_standardized_param_space(
            dict_param_matrix=np.asarray(basis_param_matrix, dtype=float),
            target_param_matrix=np.asarray(target_param_matrix, dtype=float),
        )

    for col in columns:
        values = pd.to_numeric(dict_df[col], errors="coerce").to_numpy(dtype=float)
        valid = np.isfinite(values)
        if not np.any(valid):
            out[col] = np.full(n_rows, np.nan, dtype=float)
            continue
        if use_local_linear and basis_std is not None and target_std is not None:
            pred = np.full(n_rows, np.nan, dtype=float)
            for i in range(n_rows):
                pred[i] = _local_linear_predict(
                    values=values,
                    weights_row=weights[i],
                    basis_params_std=basis_std,
                    target_param_std=target_std[i],
                    column_name=col,
                )
            out[col] = pred
        else:
            w = weights[:, valid]
            v = values[valid]
            num = w @ v
            den = w.sum(axis=1)
            out[col] = np.divide(num, den, out=np.full(n_rows, np.nan), where=den > 0)
    return out


def _round_count_like_columns(df: pd.DataFrame) -> None:
    """Round count-like columns in place to non-negative integers."""
    count_keywords = ("_count", "_entries_", "n_events", "selected_rows", "requested_rows", "generated_events_count")
    for col in df.columns:
        if not any(k in col for k in count_keywords):
            continue
        s = pd.to_numeric(df[col], errors="coerce")
        if s.notna().any():
            rounded = np.rint(np.clip(s.to_numpy(dtype=float), 0.0, None))
            df[col] = pd.Series(rounded, index=df.index).astype("Int64")


def _rebuild_efficiencies_string(df: pd.DataFrame) -> None:
    """Rebuild efficiencies string column when simulation efficiencies exist."""
    if "efficiencies" not in df.columns:
        return
    needed = [f"eff_sim_{i}" for i in range(1, 5)]
    if not all(c in df.columns for c in needed):
        return

    eff_matrix = df[needed].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    df["efficiencies"] = pd.Series(eff_matrix.tolist(), index=df.index).astype(str)


def _rebuild_weighted_step12_helper_columns(df: pd.DataFrame) -> dict[str, object]:
    """
    Rebuild deterministic STEP 1.2 helper columns after weighted STEP 3.2 output.

    In weighted mode, STEP 3.2 ultimately forces the parameter-space columns to the
    STEP 3.1 targets. Columns derived deterministically from those parameters must
    therefore be rebuilt from the final target values rather than kept from the
    independently interpolated numeric feature blend.
    """
    info: dict[str, object] = {
        "applied": False,
        "synced_eff_alias_columns": [],
        "rebuilt_efficiency_product_columns": [],
        "rebuilt_flux_proxy_columns": [],
    }

    eff_source_cols: list[str] = []
    for plane in (1, 2, 3, 4):
        sim_col = f"eff_sim_{plane}"
        alias_col = f"eff_p{plane}"
        if sim_col not in df.columns:
            eff_source_cols = []
            break
        sim_vals = pd.to_numeric(df[sim_col], errors="coerce")
        if alias_col in df.columns:
            df[alias_col] = sim_vals
            casted = pd.to_numeric(df[alias_col], errors="coerce")
            info["synced_eff_alias_columns"].append(alias_col)
            eff_source_cols.append(alias_col)
        else:
            eff_source_cols.append(sim_col)

    if len(eff_source_cols) != 4:
        return info

    eff_vals = {
        col: pd.to_numeric(df[col], errors="coerce")
        for col in eff_source_cols
    }
    eff_matrix = pd.DataFrame(eff_vals, index=df.index)
    valid_all = eff_matrix.notna().all(axis=1)
    prod_specs = {
        "efficiency_product_4planes": eff_source_cols,
        "efficiency_product_123": eff_source_cols[:3],
        "efficiency_product_234": eff_source_cols[1:],
        "efficiency_product_12": eff_source_cols[:2],
        "efficiency_product_34": eff_source_cols[2:],
    }
    for out_col, src_cols in prod_specs.items():
        if len(src_cols) == 4:
            prod = eff_matrix[src_cols].prod(axis=1, min_count=4).where(valid_all, np.nan)
        else:
            prod = pd.to_numeric(df[src_cols[0]], errors="coerce")
            for src_col in src_cols[1:]:
                prod = prod * pd.to_numeric(df[src_col], errors="coerce")
        df[out_col] = prod
        info["rebuilt_efficiency_product_columns"].append(out_col)

    if "events_per_second_global_rate" in df.columns:
        rate = pd.to_numeric(df["events_per_second_global_rate"], errors="coerce")
        proxy_specs = {
            "flux_proxy_rate_div_effprod": "efficiency_product_4planes",
            "flux_proxy_rate_div_effprod_123": "efficiency_product_123",
            "flux_proxy_rate_div_effprod_234": "efficiency_product_234",
            "flux_proxy_rate_div_effprod_12": "efficiency_product_12",
            "flux_proxy_rate_div_effprod_34": "efficiency_product_34",
        }
        for proxy_col, prod_col in proxy_specs.items():
            if prod_col not in df.columns:
                continue
            prod = pd.to_numeric(df[prod_col], errors="coerce")
            proxy = pd.Series(np.nan, index=df.index, dtype=float)
            valid = prod.notna() & (prod > 0.0) & rate.notna()
            proxy.loc[valid] = rate.loc[valid] / prod.loc[valid]
            df[proxy_col] = proxy
            info["rebuilt_flux_proxy_columns"].append(proxy_col)

    info["applied"] = bool(
        info["synced_eff_alias_columns"]
        or info["rebuilt_efficiency_product_columns"]
        or info["rebuilt_flux_proxy_columns"]
    )
    return info


def _load_trigger_type_consistency_catalog() -> tuple[str, list[str]]:
    """Read trigger-type consistency selector from config_step_2.1_columns.json when present."""
    prefix = "last"
    trigger_types: list[str] = []
    if not CONFIG_COLUMNS_PATH.exists():
        return prefix, trigger_types
    try:
        raw = json.loads(CONFIG_COLUMNS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return prefix, trigger_types
    prefix = str(raw.get("prefix", "last")).strip() or "last"
    categories = raw.get("categories", {})
    if not isinstance(categories, dict):
        return prefix, trigger_types
    trigger_cfg = categories.get("trigger_type", {})
    if not isinstance(trigger_cfg, dict):
        return prefix, trigger_types
    if trigger_cfg.get("enabled") is False:
        return prefix, trigger_types
    raw_types = trigger_cfg.get("trigger_types", [])
    if isinstance(raw_types, list):
        trigger_types = [str(x).strip() for x in raw_types if str(x).strip()]
    return prefix, trigger_types


def _resolve_tt_rate_columns_for_consistency(df: pd.DataFrame) -> tuple[list[str], str | None, list[str]]:
    """Resolve TT-rate columns used to enforce synthetic global-rate consistency."""
    col_map: dict[str, dict[str, str]] = {}
    for col in df.columns:
        m = TT_RATE_COLUMN_RE.match(str(col))
        if not m:
            continue
        prefix = str(m.group("prefix"))
        trigger = str(m.group("trigger"))
        col_map.setdefault(prefix, {})[trigger] = str(col)

    if not col_map:
        return [], None, []

    pref_selector, trigger_allowlist = _load_trigger_type_consistency_catalog()
    pref_selector_norm = pref_selector.strip().lower()

    selected_prefix: str | None = None
    if pref_selector_norm in {"last", "latest"}:
        for cand in ("post", "fit"):
            if cand in col_map:
                selected_prefix = cand
                break
        if selected_prefix is None:
            selected_prefix = sorted(col_map.keys())[-1]
    else:
        for key in col_map:
            if key.lower() == pref_selector_norm:
                selected_prefix = key
                break
        if selected_prefix is None:
            # Fallback to prefix carrying most columns.
            selected_prefix = max(col_map.keys(), key=lambda k: len(col_map.get(k, {})))

    available = col_map.get(selected_prefix, {})
    if not available:
        return [], selected_prefix, []

    if trigger_allowlist:
        selected_triggers = [t for t in trigger_allowlist if t in available]
    else:
        selected_triggers = sorted(available.keys(), key=lambda x: (len(x), x))
    cols = [available[t] for t in selected_triggers]
    return cols, selected_prefix, selected_triggers


def _collect_histogram_rate_columns(df: pd.DataFrame) -> list[str]:
    """Return histogram-bin rate columns sorted by bin index."""
    pairs: list[tuple[int, str]] = []
    for col in df.columns:
        m = HIST_RATE_COLUMN_RE.match(str(col))
        if not m:
            continue
        if str(col) == "events_per_second_global_rate":
            continue
        pairs.append((int(m.group("bin")), str(col)))
    pairs.sort(key=lambda x: x[0])
    return [c for _, c in pairs]


def _tilt_histogram_probabilities_to_target_mean(
    probs: np.ndarray,
    bins: np.ndarray,
    target_mean: float,
    *,
    max_iter: int = 80,
) -> np.ndarray:
    """Minimal-shape adjustment (exponential tilting) to match target histogram mean."""
    p = np.asarray(probs, dtype=float).reshape(-1)
    k = np.asarray(bins, dtype=float).reshape(-1)
    if p.size == 0 or p.size != k.size or not np.isfinite(target_mean):
        return p
    p = np.clip(p, 0.0, None)
    s = float(np.sum(p))
    if s <= 0.0:
        return p
    p = p / s
    k_min = float(np.min(k))
    k_max = float(np.max(k))
    tgt = float(np.clip(float(target_mean), k_min, k_max))

    eps = 1e-12

    def _mean_at(lam: float) -> tuple[float, np.ndarray]:
        # Stable normalization in log-space.
        logw = np.log(np.clip(p, eps, None)) + float(lam) * k
        logw = logw - float(np.max(logw))
        w = np.exp(logw)
        w_sum = float(np.sum(w))
        if w_sum <= 0.0 or not np.isfinite(w_sum):
            return float("nan"), p
        q = w / w_sum
        mu = float(np.sum(q * k))
        return mu, q

    mu0 = float(np.sum(p * k))
    if abs(mu0 - tgt) <= 1e-10:
        return p

    lo, hi = -40.0, 40.0
    mu_lo, q_lo = _mean_at(lo)
    mu_hi, q_hi = _mean_at(hi)
    if not np.isfinite(mu_lo) or not np.isfinite(mu_hi):
        return p
    if tgt <= mu_lo:
        return q_lo
    if tgt >= mu_hi:
        return q_hi

    q_mid = p
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        mu_mid, q_mid = _mean_at(mid)
        if not np.isfinite(mu_mid):
            break
        if abs(mu_mid - tgt) <= 1e-8:
            return q_mid
        if mu_mid < tgt:
            lo = mid
        else:
            hi = mid
    return q_mid


def _enforce_rate_consistency_constraints(
    out_df: pd.DataFrame,
    *,
    target_rate: np.ndarray,
    tt_rate_columns: list[str] | None,
    histogram_rate_columns: list[str] | None,
) -> dict:
    """Enforce synthetic row consistency between rate-like features and target global rate."""
    info: dict = {
        "enabled": True,
        "tt_rate_columns_count": 0,
        "histogram_rate_columns_count": 0,
        "tt_target_blend": float(CANONICAL_TT_RATE_CONSISTENCY_BLEND),
        "hist_mean_target_blend": float(CANONICAL_HIST_RATE_MEAN_CONSISTENCY_BLEND),
    }
    rates = np.asarray(target_rate, dtype=float).reshape(-1)
    n_rows = len(out_df)
    if rates.size != n_rows:
        info["enabled"] = False
        info["reason"] = "target_rate_length_mismatch"
        return info

    # 1) Trigger-type rates: scale selected TT channels to match target global-rate trend.
    tt_cols = [c for c in (tt_rate_columns or []) if c in out_df.columns]
    info["tt_rate_columns_count"] = int(len(tt_cols))
    if tt_cols:
        tt_matrix = (
            out_df[tt_cols]
            .apply(pd.to_numeric, errors="coerce")
            .to_numpy(dtype=float)
        )
        info["tt_negative_entries_clipped"] = int(np.sum(np.isfinite(tt_matrix) & (tt_matrix < 0.0)))
        tt_matrix = np.where(np.isfinite(tt_matrix), np.clip(tt_matrix, 0.0, None), np.nan)
        tt_sum_before = np.nansum(tt_matrix, axis=1)
        blend_tt = float(np.clip(CANONICAL_TT_RATE_CONSISTENCY_BLEND, 0.0, 1.0))
        if blend_tt > 0.0:
            desired_tt_sum = tt_sum_before + blend_tt * (rates - tt_sum_before)
            valid = (
                np.isfinite(rates)
                & np.isfinite(tt_sum_before)
                & np.isfinite(desired_tt_sum)
                & (tt_sum_before > 1e-12)
            )
            scale = np.ones(n_rows, dtype=float)
            scale[valid] = desired_tt_sum[valid] / tt_sum_before[valid]
            tt_matrix = np.where(np.isfinite(tt_matrix), tt_matrix * scale[:, None], tt_matrix)
        out_df.loc[:, tt_cols] = tt_matrix
        tt_sum_after = np.nansum(tt_matrix, axis=1)
        m_before = np.isfinite(tt_sum_before) & np.isfinite(rates)
        m_after = np.isfinite(tt_sum_after) & np.isfinite(rates)
        info["tt_sum_rate_mae_before_hz"] = (
            float(np.mean(np.abs(tt_sum_before[m_before] - rates[m_before])))
            if np.any(m_before)
            else None
        )
        info["tt_sum_rate_mae_after_hz"] = (
            float(np.mean(np.abs(tt_sum_after[m_after] - rates[m_after])))
            if np.any(m_after)
            else None
        )

    # 2) Histogram rates: keep shape but tilt to target mean == target global rate.
    hist_cols = [c for c in (histogram_rate_columns or []) if c in out_df.columns]
    info["histogram_rate_columns_count"] = int(len(hist_cols))
    if hist_cols:
        bins = np.array([int(HIST_RATE_COLUMN_RE.match(c).group("bin")) for c in hist_cols], dtype=float)
        raw_hist = out_df[hist_cols].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
        info["hist_negative_entries_clipped"] = int(np.sum(np.isfinite(raw_hist) & (raw_hist < 0.0)))
        hist = np.where(np.isfinite(raw_hist), np.clip(raw_hist, 0.0, None), 0.0)

        sum_before = np.nansum(hist, axis=1)
        mean_before = np.divide(
            np.nansum(hist * bins[None, :], axis=1),
            sum_before,
            out=np.full(n_rows, np.nan, dtype=float),
            where=sum_before > 0.0,
        )

        hist_adj = hist.copy()
        blend_hist = float(np.clip(CANONICAL_HIST_RATE_MEAN_CONSISTENCY_BLEND, 0.0, 1.0))
        if blend_hist > 0.0:
            desired_mean = mean_before + blend_hist * (rates - mean_before)
            for i in range(n_rows):
                if not np.isfinite(desired_mean[i]):
                    continue
                row = hist_adj[i]
                mass = float(np.sum(row))
                if mass <= 0.0:
                    continue
                probs = row / mass
                probs_adj = _tilt_histogram_probabilities_to_target_mean(
                    probs,
                    bins,
                    float(desired_mean[i]),
                )
                hist_adj[i] = np.clip(probs_adj, 0.0, None) * mass
        out_df.loc[:, hist_cols] = hist_adj

        sum_after = np.nansum(hist_adj, axis=1)
        mean_after = np.divide(
            np.nansum(hist_adj * bins[None, :], axis=1),
            sum_after,
            out=np.full(n_rows, np.nan, dtype=float),
            where=sum_after > 0.0,
        )
        m_before = np.isfinite(mean_before) & np.isfinite(rates)
        m_after = np.isfinite(mean_after) & np.isfinite(rates)
        info["hist_mean_rate_mae_before_hz"] = (
            float(np.mean(np.abs(mean_before[m_before] - rates[m_before])))
            if np.any(m_before)
            else None
        )
        info["hist_mean_rate_mae_after_hz"] = (
            float(np.mean(np.abs(mean_after[m_after] - rates[m_after])))
            if np.any(m_after)
            else None
        )

    return info


def _make_synthetic_dataset(
    dictionary_df: pd.DataFrame,
    template_df: pd.DataFrame,
    time_df: pd.DataFrame,
    weights: np.ndarray,
    basis_param_matrix: np.ndarray,
    target_param_matrix: np.ndarray,
    *,
    feature_generation_mode: str,
    flux_col: str | None,
    eff_col: str | None,
    time_rate_col: str | None,
    time_events_col: str | None,
    time_duration_col: str,
    interpolation_aggregation: str,
    flux_output_values: np.ndarray | None = None,
    eff_output_values: np.ndarray | None = None,
    tt_rate_columns_for_consistency: list[str] | None = None,
    histogram_rate_columns_for_consistency: list[str] | None = None,
) -> tuple[pd.DataFrame, np.ndarray]:
    """Create synthetic dataset preserving template morphology."""
    n_targets = len(time_df)
    template_cols = list(template_df.columns)
    common_cols = [c for c in template_cols if c in dictionary_df.columns]
    out = pd.DataFrame(index=np.arange(n_targets), columns=template_cols)

    # Dominant row gives categorical/non-numeric morphology.
    dominant_idx = np.argmax(weights, axis=1)
    copy_closest_basis_row = feature_generation_mode in {"closest_point", "dataset_data_curve"}
    if copy_closest_basis_row:
        for col in common_cols:
            out[col] = dictionary_df[col].to_numpy()[dominant_idx]
    else:
        for col in common_cols:
            if pd.api.types.is_numeric_dtype(dictionary_df[col]):
                continue
            out[col] = dictionary_df[col].to_numpy()[dominant_idx]

        numeric_cols = [c for c in common_cols if pd.api.types.is_numeric_dtype(dictionary_df[c])]
        numeric_values = _weighted_numeric_columns(
            weights,
            dictionary_df,
            numeric_cols,
            interpolation_aggregation=interpolation_aggregation,
            basis_param_matrix=basis_param_matrix,
            target_param_matrix=target_param_matrix,
        )
        for col, values in numeric_values.items():
            out[col] = values

    # Parameter-space target overrides from STEP 3.1.
    target_flux = (
        pd.to_numeric(time_df[flux_col], errors="coerce")
        if flux_col is not None and flux_col in time_df.columns
        else pd.Series(np.nan, index=time_df.index, dtype=float)
    )
    target_eff = (
        pd.to_numeric(time_df[eff_col], errors="coerce")
        if eff_col is not None and eff_col in time_df.columns
        else pd.Series(np.nan, index=time_df.index, dtype=float)
    )
    if time_rate_col is not None and time_rate_col in time_df.columns:
        target_rate_from_time = pd.to_numeric(time_df[time_rate_col], errors="coerce")
    else:
        target_rate_from_time = pd.Series(np.nan, index=time_df.index, dtype=float)
    if time_events_col is not None and time_events_col in time_df.columns:
        target_events_from_time = pd.to_numeric(time_df[time_events_col], errors="coerce")
    else:
        target_events_from_time = pd.Series(np.nan, index=time_df.index, dtype=float)
    target_duration = pd.to_numeric(time_df[time_duration_col], errors="coerce")
    target_output_flux = target_flux
    target_output_eff = target_eff
    if flux_output_values is not None and len(flux_output_values) == n_targets:
        target_output_flux = pd.Series(np.asarray(flux_output_values, dtype=float), index=time_df.index)
    if eff_output_values is not None and len(eff_output_values) == n_targets:
        target_output_eff = pd.Series(np.asarray(eff_output_values, dtype=float), index=time_df.index)

    if copy_closest_basis_row:
        if flux_col is not None and flux_col in dictionary_df.columns:
            output_flux = pd.Series(
                pd.to_numeric(dictionary_df.iloc[dominant_idx][flux_col], errors="coerce").to_numpy(dtype=float),
                index=time_df.index,
            )
        else:
            output_flux = pd.Series(np.nan, index=time_df.index, dtype=float)
        if eff_col is not None and eff_col in dictionary_df.columns:
            output_eff = pd.Series(
                pd.to_numeric(dictionary_df.iloc[dominant_idx][eff_col], errors="coerce").to_numpy(dtype=float),
                index=time_df.index,
            )
        else:
            output_eff = pd.Series(np.nan, index=time_df.index, dtype=float)
    else:
        output_flux = target_output_flux
        output_eff = target_output_eff

    # Global rate is a weighted feature-space output from STEP 3.2.
    weighted_rate = pd.Series(np.nan, index=out.index, dtype=float)
    if "events_per_second_global_rate" in out.columns:
        weighted_rate = pd.to_numeric(out["events_per_second_global_rate"], errors="coerce")
    if weighted_rate.notna().sum() == 0:
        tt_cols_for_rate = [c for c in out.columns if TT_RATE_COLUMN_RE.match(str(c))]
        if tt_cols_for_rate:
            tt_sum = np.zeros(len(out), dtype=float)
            valid_any = np.zeros(len(out), dtype=bool)
            for c in tt_cols_for_rate:
                v = pd.to_numeric(out[c], errors="coerce").to_numpy(dtype=float)
                finite = np.isfinite(v)
                tt_sum[finite] += v[finite]
                valid_any |= finite
            weighted_rate = pd.Series(np.where(valid_any, tt_sum, np.nan), index=out.index, dtype=float)
    if weighted_rate.notna().sum() == 0:
        weighted_rate = target_rate_from_time.copy()
    if weighted_rate.notna().sum() == 0:
        fallback = 1.0
        weighted_rate = pd.Series(np.full(len(out), fallback, dtype=float), index=out.index)

    weighted_rate_arr = pd.to_numeric(weighted_rate, errors="coerce").to_numpy(dtype=float)
    finite_rate = np.isfinite(weighted_rate_arr)
    if np.any(finite_rate):
        med_rate = float(np.nanmedian(weighted_rate_arr[finite_rate]))
        if not np.isfinite(med_rate) or med_rate <= 0.0:
            med_rate = 1.0
    else:
        med_rate = 1.0
    weighted_rate_arr = np.where(np.isfinite(weighted_rate_arr), weighted_rate_arr, med_rate)
    weighted_rate_arr = np.maximum(weighted_rate_arr, 1e-9)
    weighted_rate = pd.Series(weighted_rate_arr, index=out.index, dtype=float)

    # Keep synthetic rate-like feature columns internally consistent with the
    # STEP 3.2 weighted global-rate trajectory.
    rate_consistency_info = _enforce_rate_consistency_constraints(
        out_df=out,
        target_rate=weighted_rate.to_numpy(dtype=float),
        tt_rate_columns=tt_rate_columns_for_consistency,
        histogram_rate_columns=histogram_rate_columns_for_consistency,
    )

    if copy_closest_basis_row and "n_events" in out.columns:
        output_events = pd.to_numeric(out["n_events"], errors="coerce")
    else:
        duration_arr = pd.to_numeric(target_duration, errors="coerce").to_numpy(dtype=float)
        events_from_rate = np.rint(
            np.clip(weighted_rate_arr, 0.0, None)
            * np.where(np.isfinite(duration_arr), np.maximum(duration_arr, 0.0), 0.0)
        )
        events_from_rate = np.where(np.isfinite(events_from_rate), np.maximum(events_from_rate, 0.0), np.nan)
        if np.isfinite(events_from_rate).any():
            output_events = pd.Series(events_from_rate, index=time_df.index, dtype=float)
        else:
            output_events = target_events_from_time.copy()

    if flux_col is not None:
        out[flux_col] = output_flux
    if eff_col is not None:
        out[eff_col] = output_eff
    if CANONICAL_FLUX_COLUMN in out.columns:
        out["flux"] = pd.to_numeric(out[CANONICAL_FLUX_COLUMN], errors="coerce")
    elif flux_col is not None:
        out["flux"] = output_flux
    elif "flux" not in out.columns:
        out["flux"] = np.nan
    if CANONICAL_EFF_COLUMN in out.columns:
        out["eff"] = pd.to_numeric(out[CANONICAL_EFF_COLUMN], errors="coerce")
    elif eff_col is not None:
        out["eff"] = output_eff
    elif "eff" not in out.columns:
        out["eff"] = np.nan
    out["events_per_second_global_rate"] = weighted_rate
    out["n_events"] = pd.to_numeric(output_events, errors="coerce").round().astype("Int64")
    for c in ("selected_rows", "requested_rows", "generated_events_count"):
        if c in out.columns and not copy_closest_basis_row:
            out[c] = pd.to_numeric(output_events, errors="coerce").round().astype("Int64")
    for c in ("count_rate_denominator_seconds", "events_per_second_total_seconds"):
        if c in out.columns and not copy_closest_basis_row:
            out[c] = target_duration
    if "is_dictionary_entry" in out.columns:
        out["is_dictionary_entry"] = False

    # Keep synthetic identifiers consistent and non-colliding.
    synthetic_ids = np.array([f"synthetic_{i:06d}" for i in range(1, n_targets + 1)], dtype=object)
    if "filename_base" in out.columns:
        out["filename_base"] = synthetic_ids
    for c in ("param_hash_x", "param_hash_y"):
        if c in out.columns:
            out[c] = synthetic_ids

    _rebuild_efficiencies_string(out)
    _round_count_like_columns(out)

    # Add time/traceability columns in one concat to avoid dataframe fragmentation.
    extras = pd.DataFrame({
        "file_index": pd.to_numeric(pd.Series(time_df.get("file_index"), index=time_df.index), errors="coerce").astype("Int64"),
        "time_start_utc": pd.Series(time_df.get("time_start_utc"), index=time_df.index),
        "time_end_utc": pd.Series(time_df.get("time_end_utc"), index=time_df.index),
        "time_utc": pd.Series(time_df.get("time_utc"), index=time_df.index),
        "elapsed_hours_start": pd.to_numeric(pd.Series(time_df.get("elapsed_hours_start"), index=time_df.index), errors="coerce"),
        "elapsed_hours_end": pd.to_numeric(pd.Series(time_df.get("elapsed_hours_end"), index=time_df.index), errors="coerce"),
        "elapsed_hours": pd.to_numeric(pd.Series(time_df.get("elapsed_hours"), index=time_df.index), errors="coerce"),
        "duration_seconds": target_duration,
        "target_events_per_file": pd.to_numeric(pd.Series(time_df.get("target_events_per_file"), index=time_df.index), errors="coerce").astype("Int64"),
        "n_events_expected": pd.to_numeric(pd.Series(time_df.get("n_events_expected"), index=time_df.index), errors="coerce"),
        "global_rate_hz_source": weighted_rate,
        "dominant_dictionary_index": dominant_idx,
        "step32_feature_generation_mode": np.full(n_targets, feature_generation_mode, dtype=object),
        "step31_curve_data_mode": pd.Series(time_df.get("step31_curve_data_mode"), index=time_df.index).fillna(feature_generation_mode),
    }, index=out.index)
    if "filename_base" in dictionary_df.columns:
        extras["dominant_dictionary_filename_base"] = dictionary_df["filename_base"].astype(str).to_numpy()[dominant_idx]

    out = pd.concat([out, extras], axis=1).copy()
    out.attrs["rate_consistency_info"] = rate_consistency_info
    return out, dominant_idx


def _plot_highlight_contributions(
    complete_df: pd.DataFrame | None,
    time_df: pd.DataFrame,
    dictionary_df: pd.DataFrame,
    weights: np.ndarray,
    event_allowed_mask: np.ndarray | None,
    basis_label: str,
    highlight_idx: int,
    parameter_space_cols: list[str],
    path: Path,
) -> None:
    """Plot one-event weighted dictionary contributions in lower-triangle parameter space."""
    n = len(parameter_space_cols)
    if n <= 0:
        return

    fig, axes = plt.subplots(n, n, figsize=(3.0 * n, 3.0 * n), squeeze=False)

    contrib_all = weights[highlight_idx] * 100.0
    if event_allowed_mask is None:
        event_allowed = np.ones_like(contrib_all, dtype=bool)
    else:
        event_allowed = np.asarray(event_allowed_mask, dtype=bool)
        if event_allowed.ndim != 1 or event_allowed.shape[0] != contrib_all.shape[0]:
            event_allowed = np.ones_like(contrib_all, dtype=bool)

    # Global masks reused for all pair panels.
    finite_contrib = np.isfinite(contrib_all)
    allowed_nonzero_base = event_allowed & (contrib_all > 0.0) & finite_contrib
    vmax = float(np.nanmax(contrib_all[allowed_nonzero_base])) if np.any(allowed_nonzero_base) else 1.0
    vmax = max(vmax, 1e-12)
    norm = plt.Normalize(vmin=0.0, vmax=vmax)
    cmap = plt.get_cmap("viridis")

    for i, y_col in enumerate(parameter_space_cols):
        for j, x_col in enumerate(parameter_space_cols):
            ax = axes[i, j]
            if i < j:
                ax.axis("off")
                continue

            bx = pd.to_numeric(dictionary_df.get(x_col), errors="coerce")
            by = pd.to_numeric(dictionary_df.get(y_col), errors="coerce")
            tx = pd.to_numeric(time_df.get(x_col), errors="coerce")
            ty = pd.to_numeric(time_df.get(y_col), errors="coerce")

            if i == j:
                b = bx.dropna()
                if not b.empty:
                    ax.hist(b, bins=34, color="#808080", alpha=0.34, label="Dictionary")
                m_weighted_1d = bx.notna() & allowed_nonzero_base
                if m_weighted_1d.any():
                    ax.hist(
                        bx[m_weighted_1d],
                        bins=34,
                        weights=contrib_all[m_weighted_1d],
                        color="#D62728",
                        alpha=0.35,
                        label="Weighted mass [%]",
                    )
                hx = pd.to_numeric(pd.Series([tx.iloc[highlight_idx]]), errors="coerce").iloc[0]
                if np.isfinite(hx):
                    ax.axvline(float(hx), color="#D62728", linestyle="--", linewidth=1.0)
                if i == 0 and j == 0:
                    ax.legend(loc="best", fontsize=7)
                ax.set_ylabel("count / weight")
            else:
                m_basis = bx.notna() & by.notna() & finite_contrib
                m_excluded = m_basis & ~event_allowed
                m_allowed_zero = m_basis & event_allowed & (contrib_all <= 0.0)
                m_weighted = m_basis & allowed_nonzero_base

                if m_excluded.any():
                    ax.scatter(
                        bx[m_excluded],
                        by[m_excluded],
                        s=14,
                        marker="x",
                        color="lightgray",
                        alpha=0.80,
                        linewidths=0.8,
                        label=("Excluded by event constraint" if (i == 1 and j == 0) else None),
                        zorder=0,
                    )
                if m_allowed_zero.any():
                    ax.scatter(
                        bx[m_allowed_zero],
                        by[m_allowed_zero],
                        s=12,
                        color="#C7CBD1",
                        alpha=0.65,
                        linewidths=0.0,
                        label=("Allowed, zero weight" if (i == 1 and j == 0) else None),
                        zorder=0,
                    )
                if m_weighted.any():
                    cvals = contrib_all[m_weighted]
                    ax.scatter(
                        bx[m_weighted],
                        by[m_weighted],
                        c=cvals,
                        cmap=cmap,
                        norm=norm,
                        s=24 + 260 * (cvals / vmax),
                        alpha=0.88,
                        edgecolors="black",
                        linewidths=0.25,
                        label=("Weighted dictionary points" if (i == 1 and j == 0) else None),
                        zorder=1,
                    )

                if complete_df is not None and not complete_df.empty:
                    cx = pd.to_numeric(complete_df.get(x_col), errors="coerce")
                    cy = pd.to_numeric(complete_df.get(y_col), errors="coerce")
                    m_comp = cx.notna() & cy.notna()
                    if m_comp.any():
                        ax.plot(
                            cx[m_comp],
                            cy[m_comp],
                            color="#1f77b4",
                            linewidth=1.1,
                            alpha=0.85,
                            label=("Complete curve" if (i == 1 and j == 0) else None),
                            zorder=2,
                        )

                m_time = tx.notna() & ty.notna()
                if m_time.any():
                    ax.scatter(
                        tx[m_time],
                        ty[m_time],
                        s=14,
                        facecolor="white",
                        edgecolor="black",
                        linewidth=0.5,
                        label=("Discretized curve" if (i == 1 and j == 0) else None),
                        zorder=3,
                    )

                hx = pd.to_numeric(pd.Series([tx.iloc[highlight_idx]]), errors="coerce").iloc[0]
                hy = pd.to_numeric(pd.Series([ty.iloc[highlight_idx]]), errors="coerce").iloc[0]
                if np.isfinite(hx) and np.isfinite(hy):
                    ax.scatter(
                        [float(hx)],
                        [float(hy)],
                        s=85,
                        color="#D62728",
                        marker="X",
                        label=(f"Highlight idx {highlight_idx}" if (i == 1 and j == 0) else None),
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

    legend_anchor = axes[min(1, n - 1), 0]
    handles, labels = legend_anchor.get_legend_handles_labels()
    if handles:
        fig.legend(handles, labels, loc="upper right", fontsize=8, framealpha=0.9)

    if np.any(allowed_nonzero_base):
        sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
        sm.set_array([])
        cbar = fig.colorbar(sm, ax=axes, fraction=0.022, pad=0.02)
        cbar.set_label("Contribution [%]")

    fig.suptitle(
        f"{basis_label} one-event contributions (highlight idx {highlight_idx}) in parameter space",
        fontsize=12,
    )
    fig.subplots_adjust(left=0.07, right=0.93, bottom=0.06, top=0.95, wspace=0.08, hspace=0.10)
    _save_figure(fig, path, dpi=160)
    plt.close(fig)


def _plot_time_series_overview(
    complete_df: pd.DataFrame | None,
    time_df: pd.DataFrame,
    synthetic_df: pd.DataFrame,
    flux_col: str | None,
    eff_col: str | None,
    time_rate_col: str | None,
    interpolated_flux: np.ndarray | None,
    interpolated_eff: np.ndarray | None,
    interpolated_label: str,
    show_diagnostic_center: bool,
    path: Path,
) -> None:
    """Plot complete/discretized/synthetic flux-eff-rate comparison."""
    from matplotlib.lines import Line2D

    fig, axes = plt.subplots(3, 1, figsize=(10, 8.5), sharex=True)

    x_disc = pd.to_numeric(time_df.get("elapsed_hours"), errors="coerce")
    x_syn = pd.to_numeric(synthetic_df.get("elapsed_hours"), errors="coerce")
    flux_plot_col = None
    for candidate in (flux_col, CANONICAL_FLUX_COLUMN, "flux"):
        if isinstance(candidate, str) and candidate and (
            candidate in time_df.columns
            or candidate in synthetic_df.columns
            or (complete_df is not None and candidate in complete_df.columns)
        ):
            flux_plot_col = candidate
            break
    y_flux_disc = pd.to_numeric(time_df.get(flux_plot_col), errors="coerce")
    y_syn_flux = pd.to_numeric(synthetic_df.get(flux_plot_col), errors="coerce")

    if flux_plot_col is not None and complete_df is not None and not complete_df.empty:
        x_comp = pd.to_numeric(complete_df.get("elapsed_hours"), errors="coerce")
        y_flux_comp = pd.to_numeric(complete_df.get(flux_plot_col), errors="coerce")
        m0 = x_comp.notna() & y_flux_comp.notna()
        if m0.any():
            axes[0].plot(
                x_comp[m0],
                y_flux_comp[m0],
                color="#1f77b4",
                alpha=0.75,
                linewidth=1.0,
                label="Complete curve",
            )

    m0d = x_disc.notna() & y_flux_disc.notna()
    if flux_plot_col is not None and m0d.any():
        axes[0].scatter(
            x_disc[m0d],
            y_flux_disc[m0d],
            s=18,
            facecolors="white",
            edgecolors="#1f77b4",
            linewidths=0.8,
            label="Discretized",
        )

    m0s = x_syn.notna() & y_syn_flux.notna()
    if flux_plot_col is not None and m0s.any():
        axes[0].plot(
            x_syn[m0s],
            y_syn_flux[m0s],
            color="#D62728",
            linewidth=1.1,
            linestyle="-",
            alpha=0.9,
            label="Synthetic output",
        )

    has_interp_flux = False
    if flux_plot_col is not None and show_diagnostic_center and interpolated_flux is not None:
        y_flux_interp = pd.to_numeric(pd.Series(interpolated_flux), errors="coerce")
        m0i = x_disc.notna() & y_flux_interp.notna()
        if m0i.any():
            has_interp_flux = True
            axes[0].plot(
                x_disc[m0i],
                y_flux_interp[m0i],
                color="#8C8C8C",
                linewidth=0.9,
                linestyle="--",
                alpha=0.85,
                label=interpolated_label,
            )

    eff_candidates = [f"eff_sim_{i}" for i in range(1, 5)]
    if isinstance(eff_col, str) and eff_col and eff_col not in eff_candidates:
        eff_candidates.append(eff_col)
    if "eff" not in eff_candidates:
        eff_candidates.append("eff")
    eff_cols: list[str] = []
    for col in eff_candidates:
        if (
            (complete_df is not None and col in complete_df.columns)
            or col in time_df.columns
            or col in synthetic_df.columns
        ) and col not in eff_cols:
            eff_cols.append(col)
    eff_palette = ["#ff7f0e", "#d62728", "#9467bd", "#8c564b", "#2ca02c", "#17becf"]
    eff_has_complete = False
    eff_has_discretized = False
    eff_has_synthetic = False

    for idx, col in enumerate(eff_cols):
        color = eff_palette[idx % len(eff_palette)]
        if complete_df is not None and not complete_df.empty and col in complete_df.columns:
            x_comp = pd.to_numeric(complete_df.get("elapsed_hours"), errors="coerce")
            y_comp = pd.to_numeric(complete_df.get(col), errors="coerce")
            m = x_comp.notna() & y_comp.notna()
            if m.any():
                eff_has_complete = True
                axes[1].plot(
                    x_comp[m],
                    y_comp[m],
                    color=color,
                    alpha=0.70,
                    linewidth=1.0,
                )
        if col in time_df.columns:
            y_disc = pd.to_numeric(time_df.get(col), errors="coerce")
            m = x_disc.notna() & y_disc.notna()
            if m.any():
                eff_has_discretized = True
                axes[1].scatter(
                    x_disc[m],
                    y_disc[m],
                    s=16,
                    facecolors="white",
                    edgecolors=color,
                    linewidths=0.8,
                )
        if col in synthetic_df.columns:
            y_syn = pd.to_numeric(synthetic_df.get(col), errors="coerce")
            m = x_syn.notna() & y_syn.notna()
            if m.any():
                eff_has_synthetic = True
                axes[1].plot(
                    x_syn[m],
                    y_syn[m],
                    color=color,
                    linewidth=1.0,
                    linestyle="-",
                    alpha=0.90,
                )

    has_interp_eff = False
    if show_diagnostic_center and interpolated_eff is not None:
        y_eff_interp = pd.to_numeric(pd.Series(interpolated_eff), errors="coerce")
        m1i = x_disc.notna() & y_eff_interp.notna()
        if m1i.any():
            has_interp_eff = True
            axes[1].plot(
                x_disc[m1i],
                y_eff_interp[m1i],
                color="#8C8C8C",
                linewidth=0.9,
                linestyle="--",
                alpha=0.85,
                label=interpolated_label,
            )

    axes[0].set_ylabel(flux_plot_col if flux_plot_col is not None else "value")
    if flux_plot_col is None:
        axes[0].text(
            0.5,
            0.5,
            "No common flux-like column available",
            transform=axes[0].transAxes,
            ha="center",
            va="center",
            fontsize=10,
            color="#666666",
        )
        axes[0].set_title("Flux-like control unavailable")
    elif has_interp_flux:
        axes[0].set_title("Flux: complete + discretized + synthetic (+ diagnostic center)")
    else:
        axes[0].set_title("Flux: complete + discretized + synthetic")
    axes[0].grid(True, alpha=0.25)
    handles0, labels0 = axes[0].get_legend_handles_labels()
    if handles0:
        axes[0].legend(loc="best", fontsize=8, framealpha=0.92, facecolor="white")

    axes[1].set_ylabel("eff")
    if not eff_cols:
        axes[1].text(
            0.5,
            0.5,
            "No common efficiency-like column available",
            transform=axes[1].transAxes,
            ha="center",
            va="center",
            fontsize=10,
            color="#666666",
        )
        axes[1].set_title("Efficiency control unavailable")
    elif has_interp_eff:
        axes[1].set_title("Efficiencies: complete + discretized + synthetic (+ diagnostic center)")
    else:
        axes[1].set_title("Efficiencies: complete + discretized + synthetic")
    axes[1].grid(True, alpha=0.25)

    # Compact two-block legend for efficiency panel.
    style_handles: list[Line2D] = []
    if eff_has_complete:
        style_handles.append(
            Line2D([0], [0], color="#505050", linestyle="--", linewidth=1.2, label="Complete")
        )
    if eff_has_discretized:
        style_handles.append(
            Line2D(
                [0],
                [0],
                color="#505050",
                linestyle="None",
                marker="o",
                markersize=5,
                markerfacecolor="white",
                markeredgewidth=0.9,
                markeredgecolor="#505050",
                label="Discretized",
            )
        )
    if eff_has_synthetic:
        style_handles.append(
            Line2D([0], [0], color="#505050", linestyle="-", linewidth=1.2, label="Synthetic")
        )
    if has_interp_eff:
        style_handles.append(
            Line2D([0], [0], color="#8C8C8C", linestyle="--", linewidth=1.0, label=interpolated_label)
        )

    color_handles: list[Line2D] = []
    for idx, col in enumerate(eff_cols):
        color = eff_palette[idx % len(eff_palette)]
        color_handles.append(Line2D([0], [0], color=color, linewidth=2.0, label=col))

    if style_handles:
        leg_style = axes[1].legend(
            handles=style_handles,
            loc="upper left",
            fontsize=7,
            framealpha=0.93,
            facecolor="white",
            title="Series",
            title_fontsize=7,
        )
        axes[1].add_artist(leg_style)
    if color_handles:
        axes[1].legend(
            handles=color_handles,
            loc="upper right",
            fontsize=7,
            framealpha=0.93,
            facecolor="white",
            title="Efficiency",
            title_fontsize=7,
            ncol=2,
            columnspacing=0.8,
            handlelength=2.0,
        )

    # Global rate overlays: complete, discretized target, synthetic output.
    if complete_df is not None and not complete_df.empty:
        comp_rate_col = None
        for c in ("global_rate_hz_mean", "global_rate_hz", "events_per_second_global_rate"):
            if c in complete_df.columns:
                comp_rate_col = c
                break
        if comp_rate_col is not None:
            x_comp = pd.to_numeric(complete_df.get("elapsed_hours"), errors="coerce")
            y_comp_rate = pd.to_numeric(complete_df.get(comp_rate_col), errors="coerce")
            m2c = x_comp.notna() & y_comp_rate.notna()
            if m2c.any():
                axes[2].plot(
                    x_comp[m2c],
                    y_comp_rate[m2c],
                    color="#6F3CC3",
                    alpha=0.75,
                    linewidth=1.0,
                    label="Complete curve",
                )

    if time_rate_col is not None and time_rate_col in time_df.columns:
        y_disc_rate = pd.to_numeric(time_df.get(time_rate_col), errors="coerce")
        m2d = x_disc.notna() & y_disc_rate.notna()
        if m2d.any():
            axes[2].scatter(
                x_disc[m2d],
                y_disc_rate[m2d],
                s=18,
                facecolors="white",
                edgecolors="#2CA02C",
                linewidths=0.8,
                label="Discretized",
            )

    y_syn_rate = pd.to_numeric(synthetic_df.get("events_per_second_global_rate"), errors="coerce")
    if y_syn_rate.isna().all():
        syn_events = pd.to_numeric(synthetic_df.get("n_events"), errors="coerce")
        syn_dur = pd.to_numeric(synthetic_df.get("duration_seconds"), errors="coerce")
        y_syn_rate = pd.Series(
            np.divide(
                syn_events.to_numpy(dtype=float),
                syn_dur.to_numpy(dtype=float),
                out=np.full(len(synthetic_df), np.nan, dtype=float),
                where=np.isfinite(syn_dur.to_numpy(dtype=float)) & (syn_dur.to_numpy(dtype=float) > 0),
            ),
            index=synthetic_df.index,
        )
    m2s = x_syn.notna() & y_syn_rate.notna()
    if m2s.any():
        axes[2].plot(
            x_syn[m2s],
            y_syn_rate[m2s],
            color="#D62728",
            linewidth=1.1,
            linestyle="-",
            alpha=0.9,
            label="Synthetic output",
        )

    axes[2].set_xlabel("Elapsed time [hours]")
    axes[2].set_ylabel("global rate [Hz]")
    axes[2].set_title("Global rate: complete + discretized + synthetic")
    axes[2].grid(True, alpha=0.25)
    axes[2].legend(loc="best", fontsize=8, framealpha=0.92, facecolor="white")

    fig.tight_layout()
    _save_figure(fig, path, dpi=160)
    plt.close(fig)


def _load_selected_feature_columns(path: Path) -> list[str]:
    """Load ordered STEP 1.4 feature columns from JSON."""
    if not path.exists():
        log.warning("Selected feature-columns JSON not found: %s", path)
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("Could not parse selected feature-columns JSON %s: %s", path, exc)
        return []

    if isinstance(raw, dict):
        values = raw.get("selected_feature_columns", [])
    elif isinstance(raw, list):
        values = raw
    else:
        values = []

    out: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = str(item).strip()
        if not text or text in seen:
            continue
        out.append(text)
        seen.add(text)
    return out


def _feature_placeholder_label(col: str) -> str | None:
    if col == STEP12_RATE_HIST_PLACEHOLDER_COL:
        return STEP12_RATE_HIST_PLACEHOLDER_LABEL
    if col == STEP12_EFF_PLACEHOLDER_COL:
        return STEP12_EFF_PLACEHOLDER_LABEL
    return None


def _feature_placeholder_message(
    *,
    x_col: str,
    y_col: str,
    rate_hist_count: int,
    efficiency_vector_count: int,
) -> str:
    has_rate = x_col == STEP12_RATE_HIST_PLACEHOLDER_COL or y_col == STEP12_RATE_HIST_PLACEHOLDER_COL
    has_eff = x_col == STEP12_EFF_PLACEHOLDER_COL or y_col == STEP12_EFF_PLACEHOLDER_COL
    if has_rate and has_eff:
        return (
            "Suppressed grouped blocks\n"
            f"(rate histogram: {rate_hist_count}, efficiency vectors: {efficiency_vector_count})"
        )
    if has_rate:
        if rate_hist_count > 0:
            return f"Rate-histogram block suppressed\n({rate_hist_count} columns)"
        return "Rate-histogram block\nsuppressed for display"
    if has_eff:
        if efficiency_vector_count > 0:
            return f"Efficiency-vector block suppressed\n({efficiency_vector_count} columns)"
        return "Efficiency-vector block\nsuppressed for display"
    return "Suppressed grouped block"


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = str(item).strip()
        if not text or text in seen:
            continue
        out.append(text)
        seen.add(text)
    return out


def _pick_evenly_spaced_columns(columns: list[str], count: int) -> list[str]:
    items = [str(col).strip() for col in columns if str(col).strip()]
    if count <= 0 or not items:
        return []
    if len(items) <= count:
        return items
    picks = np.linspace(0, len(items) - 1, num=count)
    indices = sorted({int(round(value)) for value in picks})
    return [items[idx] for idx in indices]


def _ordered_histogram_columns(columns: list[str]) -> list[str]:
    pairs: list[tuple[int, str]] = []
    for col in columns:
        match = HIST_RATE_COLUMN_RE.match(str(col))
        if match is None:
            continue
        pairs.append((int(match.group("bin")), str(col)))
    return [col for _, col in sorted(pairs)]


def _representative_efficiency_vector_columns(
    columns: list[str],
    *,
    max_groups: int,
) -> list[str]:
    grouped: dict[tuple[int, str], list[tuple[int, str]]] = {}
    for col in columns:
        match = EFF_VECTOR_COL_RE.match(str(col))
        if match is None:
            continue
        key = (int(match.group("plane")), str(match.group("axis")))
        grouped.setdefault(key, []).append((int(match.group("bin")), str(col)))

    representatives: list[str] = []
    ordered_keys = sorted(grouped)
    if max_groups > 0 and len(ordered_keys) > max_groups:
        keep_keys = _pick_evenly_spaced_columns(
            [f"{plane}:{axis}" for plane, axis in ordered_keys],
            max_groups,
        )
        keep_key_set = {
            tuple(item.split(":", 1)) for item in keep_keys
        }
        ordered_keys = [
            key for key in ordered_keys
            if (str(key[0]), str(key[1])) in keep_key_set
        ]

    for key in ordered_keys:
        bins = sorted(grouped[key])
        if not bins:
            continue
        representatives.append(bins[len(bins) // 2][1])
    return representatives


def _feature_space_axis_label(col: str) -> str:
    placeholder = _feature_placeholder_label(str(col))
    if placeholder is not None:
        return placeholder
    text = str(col)
    hist_match = HIST_RATE_COLUMN_RE.match(text)
    if hist_match is not None:
        return f"rate bin {int(hist_match.group('bin'))}"
    eff_match = EFF_VECTOR_COL_RE.match(text)
    if eff_match is not None:
        return (
            f"eff p{eff_match.group('plane')} "
            f"{eff_match.group('axis')} "
            f"bin {int(eff_match.group('bin'))}"
        )
    pretty_map = {
        "post_tt_two_plane_total_rate_hz": "post_tt 2-plane",
        "post_tt_three_plane_total_rate_hz": "post_tt 3-plane",
        "post_tt_four_plane_rate_hz": "post_tt 4-plane",
    }
    return pretty_map.get(text, text)


def _resolve_feature_space_plot_columns(
    dictionary_df: pd.DataFrame,
    synthetic_df: pd.DataFrame,
    *,
    selected_features_path: Path,
    suppressed_patterns: list[str] | None = None,
    histogram_sample_count: int = 3,
    max_efficiency_groups: int = 6,
    max_other_columns: int = 2,
) -> dict[str, object]:
    selected_feature_cols = _load_selected_feature_columns(selected_features_path)
    common_cols = set(dictionary_df.columns) & set(synthetic_df.columns)
    available_selected = [col for col in selected_feature_cols if col in common_cols]

    hist_cols = _ordered_histogram_columns(available_selected)
    eff_cols = [
        col for col in available_selected
        if EFF_VECTOR_COL_RE.match(str(col)) is not None
    ]
    other_selected = [
        col for col in available_selected
        if col not in set(hist_cols) and col not in set(eff_cols)
    ]

    hist_representatives = _pick_evenly_spaced_columns(hist_cols, histogram_sample_count)
    eff_representatives = _representative_efficiency_vector_columns(
        eff_cols,
        max_groups=max_efficiency_groups,
    )
    patterns = [str(pattern).strip() for pattern in (suppressed_patterns or []) if str(pattern).strip()]
    suppress_hist = any(
        fnmatch.fnmatchcase(col, pattern)
        for pattern in patterns
        for col in hist_cols
    )
    suppress_eff = any(
        fnmatch.fnmatchcase(col, pattern)
        for pattern in patterns
        for col in eff_cols
    )

    post_tt_candidates = [
        "post_tt_two_plane_total_rate_hz",
        "post_tt_three_plane_total_rate_hz",
        "post_tt_four_plane_rate_hz",
    ]
    # Only show these totals when they are part of the selected feature space.
    # They are ancillary in the current STEP 1.2 config and should not be
    # injected into the feature-space plot just because they exist in the table.
    post_tt_cols = [col for col in post_tt_candidates if col in available_selected]

    # Keep a compact feature-space slice that still shows the grouped curve.
    columns_used = _dedupe_preserve_order(
        post_tt_cols
        + ([STEP12_RATE_HIST_PLACEHOLDER_COL] if suppress_hist and hist_cols else hist_representatives)
        + ([STEP12_EFF_PLACEHOLDER_COL] if suppress_eff and eff_cols else eff_representatives)
        + other_selected[:max_other_columns]
    )
    display_labels = {col: _feature_space_axis_label(col) for col in columns_used}

    return {
        "selected_features_path": str(selected_features_path),
        "feature_space_lower_triangle_suppressed_patterns": patterns,
        "selected_features_requested_count": int(len(selected_feature_cols)),
        "selected_features_available_count": int(len(available_selected)),
        "histogram_columns_available_count": int(len(hist_cols)),
        "histogram_columns_representative": hist_representatives,
        "rate_hist_block_suppressed": bool(suppress_hist and hist_cols),
        "efficiency_vector_columns_available_count": int(len(eff_cols)),
        "efficiency_vector_columns_representative": eff_representatives,
        "efficiency_vector_block_suppressed": bool(suppress_eff and eff_cols),
        "post_tt_columns_included": post_tt_cols,
        "other_selected_columns_included": other_selected[:max_other_columns],
        "columns_used": columns_used,
        "column_display_labels": display_labels,
    }


def _plot_feature_space_lower_triangle(
    basis_df: pd.DataFrame,
    synthetic_df: pd.DataFrame,
    *,
    feature_cols: list[str],
    feature_labels: dict[str, str],
    rate_hist_count: int,
    efficiency_vector_count: int,
    path: Path,
) -> Path | None:
    """Plot a compact feature-space lower triangle: dictionary cloud + synthetic curve."""
    n = len(feature_cols)
    if n <= 0:
        return None

    basis_plot_df = basis_df
    if len(basis_plot_df) > 3500:
        basis_plot_df = basis_plot_df.sample(n=3500, random_state=0)

    plot_data_cols = [
        col for col in feature_cols
        if _feature_placeholder_label(col) is None
    ]
    basis_numeric = {
        col: pd.to_numeric(basis_plot_df[col], errors="coerce")
        for col in plot_data_cols
        if col in basis_plot_df.columns
    }
    synthetic_numeric = {
        col: pd.to_numeric(synthetic_df[col], errors="coerce")
        for col in plot_data_cols
        if col in synthetic_df.columns
    }
    feature_axis_limits: dict[str, tuple[float, float]] = {}
    for col in plot_data_cols:
        combined = pd.concat([basis_numeric[col], synthetic_numeric[col]], ignore_index=True).to_numpy(dtype=float)
        finite = combined[np.isfinite(combined)]
        if finite.size == 0:
            continue
        lower = float(np.min(finite))
        upper = float(np.max(finite))
        if np.isclose(lower, upper):
            pad = max(abs(lower) * 0.05, 1e-6)
            feature_axis_limits[col] = (lower - pad, upper + pad)
        else:
            feature_axis_limits[col] = (lower, upper)

    synthetic_order = np.arange(len(synthetic_df), dtype=int)
    if "elapsed_hours" in synthetic_df.columns:
        elapsed = pd.to_numeric(synthetic_df.get("elapsed_hours"), errors="coerce").to_numpy(dtype=float)
        if np.isfinite(elapsed).any():
            finite_elapsed = np.where(np.isfinite(elapsed), elapsed, np.inf)
            synthetic_order = np.argsort(finite_elapsed, kind="mergesort")

    fig, axes = plt.subplots(n, n, figsize=(2.8 * n, 2.8 * n), squeeze=False)

    for i, y_col in enumerate(feature_cols):
        for j, x_col in enumerate(feature_cols):
            ax = axes[i, j]
            if i < j:
                ax.axis("off")
                continue
            x_label = _feature_placeholder_label(x_col)
            y_label = _feature_placeholder_label(y_col)
            x_is_placeholder = x_label is not None
            y_is_placeholder = y_label is not None

            if i == j:
                if x_is_placeholder:
                    ax.set_facecolor("#F2F2F2")
                    ax.text(
                        0.5,
                        0.5,
                        _feature_placeholder_message(
                            x_col=x_col,
                            y_col=y_col,
                            rate_hist_count=rate_hist_count,
                            efficiency_vector_count=efficiency_vector_count,
                        ),
                        ha="center",
                        va="center",
                        fontsize=5.8,
                        transform=ax.transAxes,
                    )
                    if i == n - 1:
                        ax.set_xlabel(x_label, fontsize=5.3)
                    else:
                        ax.set_xticklabels([])
                    if j == 0:
                        ax.set_ylabel("count", fontsize=5.3)
                    else:
                        ax.set_yticklabels([])
                    ax.tick_params(labelsize=4.8, length=1.5)
                    ax.grid(True, alpha=0.12)
                    continue

                bx = basis_numeric[x_col]
                sx = synthetic_numeric[x_col]
                basis_series = bx.dropna()
                synthetic_series = sx.dropna()
                if not basis_series.empty:
                    ax.hist(basis_series, bins=30, color="#7a7a7a", alpha=0.33, label="Dictionary")
                if not synthetic_series.empty:
                    ax.hist(
                        synthetic_series,
                        bins=30,
                        histtype="step",
                        color="#d62728",
                        linewidth=1.5,
                        label="Synthetic curve",
                    )
                if i == 0 and j == 0:
                    ax.legend(loc="best", fontsize=7, framealpha=0.92, facecolor="white")
                ax.set_ylabel("count")
            else:
                if x_is_placeholder or y_is_placeholder:
                    ax.set_facecolor("#F7F7F7")
                    if not x_is_placeholder:
                        x_limits = feature_axis_limits.get(x_col)
                        if x_limits is not None:
                            ax.set_xlim(x_limits)
                    if not y_is_placeholder:
                        y_limits = feature_axis_limits.get(y_col)
                        if y_limits is not None:
                            ax.set_ylim(y_limits)
                    if i == n - 1:
                        ax.set_xlabel(x_label or feature_labels.get(x_col, x_col), fontsize=5.3)
                    else:
                        ax.set_xticklabels([])
                    if j == 0:
                        ax.set_ylabel(y_label or feature_labels.get(y_col, y_col), fontsize=5.3)
                    else:
                        ax.set_yticklabels([])
                    ax.tick_params(labelsize=4.8, length=1.5)
                    ax.grid(True, alpha=0.10)
                    continue

                bx = basis_numeric[x_col]
                by = basis_numeric[y_col]
                sx = synthetic_numeric[x_col]
                sy = synthetic_numeric[y_col]
                basis_mask = bx.notna() & by.notna()
                if basis_mask.any():
                    ax.scatter(
                        bx[basis_mask],
                        by[basis_mask],
                        s=6,
                        color="#7a7a7a",
                        alpha=0.14,
                        linewidths=0,
                        zorder=1,
                    )

                sx_ordered = sx.iloc[synthetic_order]
                sy_ordered = sy.iloc[synthetic_order]
                synthetic_mask = sx_ordered.notna() & sy_ordered.notna()
                if synthetic_mask.any():
                    ax.plot(
                        sx_ordered[synthetic_mask],
                        sy_ordered[synthetic_mask],
                        color="#d62728",
                        lw=1.1,
                        alpha=0.9,
                        zorder=3,
                    )
                    ax.scatter(
                        sx_ordered[synthetic_mask],
                        sy_ordered[synthetic_mask],
                        s=8,
                        color="#d62728",
                        alpha=0.45,
                        linewidths=0,
                        zorder=4,
                    )

            if not x_is_placeholder:
                x_limits = feature_axis_limits.get(x_col)
                if x_limits is not None:
                    ax.set_xlim(x_limits)
            if i > j and not y_is_placeholder:
                y_limits = feature_axis_limits.get(y_col)
                if y_limits is not None:
                    ax.set_ylim(y_limits)
            ax.grid(True, alpha=0.20)
            if i == n - 1:
                ax.set_xlabel(x_label or feature_labels.get(x_col, x_col))
            else:
                ax.set_xticklabels([])
            if j == 0 and i > 0:
                ax.set_ylabel(y_label or feature_labels.get(y_col, y_col))
            elif j != 0:
                ax.set_yticklabels([])
            ax.tick_params(labelsize=4.8, length=1.5)

    fig.suptitle(
        "STEP 3.2 feature-space lower triangle: dictionary cloud + synthetic curve",
        fontsize=12,
    )
    fig.tight_layout(rect=[0.0, 0.0, 1.0, 0.98])
    out_path = _save_figure(fig, path, dpi=170)
    plt.close(fig)
    return out_path


def _plot_parameter_space_lower_triangle(
    basis_df: pd.DataFrame,
    time_df: pd.DataFrame,
    synthetic_df: pd.DataFrame,
    complete_df: pd.DataFrame | None,
    parameter_space_cols: list[str],
    path: Path,
) -> None:
    """Plot lower-triangular parameter-space diagnostics for STEP 3.2."""
    n = len(parameter_space_cols)
    if n <= 0:
        return

    fig, axes = plt.subplots(n, n, figsize=(3.0 * n, 3.0 * n), squeeze=False)

    for i, y_col in enumerate(parameter_space_cols):
        for j, x_col in enumerate(parameter_space_cols):
            ax = axes[i, j]
            if i < j:
                ax.axis("off")
                continue

            bx = pd.to_numeric(basis_df.get(x_col), errors="coerce")
            by = pd.to_numeric(basis_df.get(y_col), errors="coerce")
            tx = pd.to_numeric(time_df.get(x_col), errors="coerce")
            ty = pd.to_numeric(time_df.get(y_col), errors="coerce")
            sx = pd.to_numeric(synthetic_df.get(x_col), errors="coerce")
            sy = pd.to_numeric(synthetic_df.get(y_col), errors="coerce")

            if i == j:
                b = bx.dropna()
                t = tx.dropna()
                if not b.empty:
                    ax.hist(b, bins=35, color="#808080", alpha=0.33, label="Basis")
                if not t.empty:
                    ax.hist(t, bins=35, color="#1f77b4", alpha=0.34, label="Time targets")
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
                        color="#7a7a7a",
                        alpha=0.15,
                        linewidths=0,
                        zorder=1,
                    )

                if complete_df is not None and not complete_df.empty:
                    cx = pd.to_numeric(complete_df.get(x_col), errors="coerce")
                    cy = pd.to_numeric(complete_df.get(y_col), errors="coerce")
                    m_complete = cx.notna() & cy.notna()
                    if m_complete.any():
                        ax.plot(
                            cx[m_complete],
                            cy[m_complete],
                            color="#1f77b4",
                            lw=1.2,
                            alpha=0.9,
                            zorder=2,
                        )

                m_time = tx.notna() & ty.notna()
                if m_time.any():
                    ax.scatter(
                        tx[m_time],
                        ty[m_time],
                        s=16,
                        facecolor="white",
                        edgecolor="black",
                        linewidth=0.5,
                        zorder=3,
                    )

                m_syn = sx.notna() & sy.notna()
                if m_syn.any():
                    ax.plot(
                        sx[m_syn],
                        sy[m_syn],
                        color="#d62728",
                        lw=1.0,
                        alpha=0.85,
                        linestyle="-",
                        zorder=4,
                    )

            ax.grid(True, alpha=0.20)
            if i == n - 1:
                ax.set_xlabel(x_col)
            if j == 0 and i > 0:
                ax.set_ylabel(y_col)

    fig.suptitle("STEP 3.2 parameter-space lower-triangle diagnostics", fontsize=12)
    fig.tight_layout(rect=[0.0, 0.0, 1.0, 0.98])
    _save_figure(fig, path, dpi=170)
    plt.close(fig)


def _plot_events_count_histogram(
    dataset_events: np.ndarray,
    basis_subset_events: np.ndarray,
    path: Path,
) -> None:
    """Plot `n_events` histograms for full dataset vs selected basis subset."""
    ds = np.asarray(dataset_events, dtype=float)
    bs = np.asarray(basis_subset_events, dtype=float)
    ds = ds[np.isfinite(ds)]
    bs = bs[np.isfinite(bs)]
    if ds.size == 0:
        return

    n_bins = int(np.clip(np.sqrt(ds.size), 18, 65))
    lo = float(np.min(ds))
    hi = float(np.max(ds))
    if hi <= lo:
        hi = lo + 1.0
    bins = np.linspace(lo, hi, n_bins + 1)

    fig, ax = plt.subplots(1, 1, figsize=(8.2, 4.8))
    ax.hist(
        ds,
        bins=bins,
        color="#9AA0A6",
        alpha=0.45,
        edgecolor="white",
        linewidth=0.6,
        label=f"Dataset (n={len(ds)})",
    )
    if bs.size:
        ax.hist(
            bs,
            bins=bins,
            color="#D95F02",
            alpha=0.55,
            edgecolor="white",
            linewidth=0.6,
            label=f"Basis subset (n={len(bs)})",
        )
        ax.hist(
            bs,
            bins=bins,
            histtype="step",
            color="#8C2D04",
            linewidth=1.2,
        )

    ax.set_xlabel("n_events")
    ax.set_ylabel("Count")
    ax.set_title("Event-count distribution: dataset vs selected basis subset")
    ax.grid(True, axis="y", alpha=0.22)
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    _save_figure(fig, path, dpi=170)
    plt.close(fig)


def main() -> int:
    """Run STEP 3.2 synthetic dataset creation."""
    parser = argparse.ArgumentParser(
        description="Step 3.2: Build synthetic dataset from dictionary and time series."
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--time-series-csv", default=None)
    parser.add_argument("--complete-curve-csv", default=None)
    parser.add_argument("--dictionary-csv", default=None)
    parser.add_argument("--dataset-template-csv", default=None)
    args = parser.parse_args()

    config = _load_config(Path(args.config))
    _clear_plots_dir()
    cfg_32 = config.get("step_3_2", {})
    cfg_13 = config.get("step_1_3", {})
    cfg_32, cfg13_weighting_keys = _merge_weighting_cfg_from_step13(cfg_32, cfg_13)
    if cfg13_weighting_keys:
        log.info(
            "Applied %d STEP 3.2 weighting key(s) from step_1_3: %s",
            len(cfg13_weighting_keys),
            ", ".join(cfg13_weighting_keys),
        )
    method_cfg = _normalize_weighting_method(cfg_32.get("weighting_method", "inverse_distance"))
    basis_source_cfg_raw = cfg_32.get("basis_source", "auto")

    # Input paths
    if args.time_series_csv:
        time_series_path = _resolve_input_path(args.time_series_csv)
    elif cfg_32.get("time_series_csv"):
        time_series_path = _resolve_input_path(str(cfg_32.get("time_series_csv")))
    else:
        time_series_path = DEFAULT_TIME_SERIES

    if args.complete_curve_csv:
        complete_curve_path = _resolve_input_path(args.complete_curve_csv)
    elif cfg_32.get("complete_curve_csv"):
        complete_curve_path = _resolve_input_path(str(cfg_32.get("complete_curve_csv")))
    else:
        complete_curve_path = DEFAULT_COMPLETE_CURVE

    if args.dictionary_csv:
        dictionary_path = _resolve_input_path(args.dictionary_csv)
    elif cfg_32.get("dictionary_csv"):
        dictionary_path = _resolve_input_path(str(cfg_32.get("dictionary_csv")))
    else:
        dictionary_path = DEFAULT_DICTIONARY

    if args.dataset_template_csv:
        template_path = _resolve_input_path(args.dataset_template_csv)
    elif cfg_32.get("dataset_template_csv"):
        template_path = _resolve_input_path(str(cfg_32.get("dataset_template_csv")))
    else:
        template_path = DEFAULT_DATASET_TEMPLATE

    if cfg_32.get("selected_feature_columns_json"):
        selected_features_path = _resolve_input_path(str(cfg_32.get("selected_feature_columns_json")))
    else:
        selected_features_path = DEFAULT_STEP14_SELECTED_FEATURES

    feature_plot_histogram_sample_count = _safe_int(
        cfg_32.get("feature_space_plot_histogram_sample_count", 3),
        3,
        minimum=1,
    )
    feature_plot_max_efficiency_groups = _safe_int(
        cfg_32.get("feature_space_plot_max_efficiency_groups", 6),
        6,
        minimum=1,
    )
    feature_plot_max_other_columns = _safe_int(
        cfg_32.get("feature_space_plot_max_other_columns", 2),
        2,
        minimum=0,
    )
    feature_space_plot_suppressed_patterns = _step12_resolve_feature_space_plot_suppression_patterns(
        config,
        step_cfg=cfg_32,
    )

    required_paths = [
        ("Time series", time_series_path),
        ("Dataset template", template_path),
    ]
    for label, p in required_paths:
        if not p.exists():
            log.error("%s CSV not found: %s", label, p)
            return 1

    time_df = pd.read_csv(time_series_path, low_memory=False)
    dictionary_df = pd.DataFrame()
    if dictionary_path.exists():
        dictionary_df = pd.read_csv(dictionary_path, low_memory=False)
    template_df = pd.read_csv(template_path, low_memory=False)
    complete_df = None
    if complete_curve_path.exists():
        complete_df = pd.read_csv(complete_curve_path, low_memory=False)

    parameter_space_spec = _load_parameter_space_spec(DEFAULT_PARAMETER_SPACE_SPEC)
    time_df, time_alias_cols = _apply_parameter_space_aliases(time_df, parameter_space_spec)
    dictionary_df, dictionary_alias_cols = _apply_parameter_space_aliases(dictionary_df, parameter_space_spec)
    template_df, template_alias_cols = _apply_parameter_space_aliases(template_df, parameter_space_spec)
    complete_alias_cols: list[str] = []
    if complete_df is not None:
        complete_df, complete_alias_cols = _apply_parameter_space_aliases(complete_df, parameter_space_spec)
    if time_alias_cols:
        log.info("Materialized STEP 1 parameter-space aliases in time series: %s", time_alias_cols)
    if dictionary_alias_cols:
        log.info("Materialized STEP 1 parameter-space aliases in dictionary: %s", dictionary_alias_cols)
    if template_alias_cols:
        log.info("Materialized STEP 1 parameter-space aliases in dataset template: %s", template_alias_cols)
    if complete_alias_cols:
        log.info("Materialized STEP 1 parameter-space aliases in complete curve: %s", complete_alias_cols)

    if time_df.empty:
        log.error("Time series CSV is empty: %s", time_series_path)
        return 1
    if template_df.empty:
        log.error("Dataset template CSV is empty: %s", template_path)
        return 1

    try:
        step31_curve_data_mode, step31_mode_explicit = _resolve_step31_curve_data_mode(time_df)
    except ValueError as exc:
        log.error("%s", exc)
        return 1

    method = method_cfg
    if step31_curve_data_mode == "dataset_data_curve":
        basis_source_cfg = "dataset"
        basis_source_auto = False
        log.info(
            "STEP 3.2 following STEP 3.1 dataset_data_curve: exact source rows will be copied from the dataset template."
        )
    else:
        if step31_mode_explicit and method_cfg == "closest_point":
            log.warning(
                "STEP 3.1 requested synthetic_data_curve; ignoring step_3_2 weighting_method=closest_point and using inverse_distance."
            )
            method = "inverse_distance"
        basis_source_cfg, basis_source_auto = _resolve_basis_source(
            basis_source_cfg_raw,
            weighting_method=method,
        )
        if basis_source_auto:
            log.info(
                "STEP 3.2 auto basis source resolved to '%s' for weighting_method=%s.",
                basis_source_cfg,
                method,
            )
    if basis_source_cfg == "dictionary" and dictionary_df.empty:
        log.error("Dictionary CSV is empty: %s", dictionary_path)
        return 1

    flux_col: str | None = None
    eff_pref = CANONICAL_EFF_COLUMN
    basis_source = basis_source_cfg
    if basis_source == "dictionary":
        basis_input_df = dictionary_df
        basis_label = "Dictionary"
        basis_path = dictionary_path
    elif basis_source == "dataset":
        basis_input_df = template_df
        basis_label = "Dataset"
        basis_path = template_path
    else:
        log.error(
            "Invalid step_3_2.basis_source='%s'. Use 'auto', 'dataset', or 'dictionary'.",
            basis_source,
        )
        return 1

    parameter_space_cfg = cfg_32.get("parameter_space_columns", None)
    try:
        parameter_space_cols = _resolve_parameter_space_columns_from_cfg(
            time_df=time_df,
            basis_df=basis_input_df,
            preferred_eff=None,
            configured_columns=parameter_space_cfg,
        )
    except KeyError as exc:
        log.error("%s", exc)
        return 1
    if not parameter_space_cols:
        log.error("No shared parameter-space columns available between time series and selected basis.")
        return 1
    flux_col = _optional_common_column(time_df, basis_input_df, CANONICAL_FLUX_COLUMN)
    eff_col_common: str | None = None
    try:
        eff_col_common = _choose_common_eff_column(time_df, basis_input_df, eff_pref)
    except KeyError:
        eff_col_common = None
    eff_col_time = eff_col_common
    eff_col_basis = eff_col_common
    if flux_col is None:
        log.info(
            "No common canonical flux column '%s' in time series and selected basis; proceeding with parameter-space columns %s.",
            CANONICAL_FLUX_COLUMN,
            parameter_space_cols,
        )
    if eff_col_common is None:
        log.info(
            "No common efficiency column found between time series and selected basis; proceeding without dedicated efficiency diagnostic axis.",
        )
    elif eff_col_common != eff_pref:
        log.info(
            "Requested efficiency column %s not available in both tables; using common column %s.",
            eff_pref,
            eff_col_common,
        )

    for legacy_key in ("time_n_events_column", "time_rate_column", "time_duration_column"):
        if cfg_32.get(legacy_key) is not None:
            log.warning(
                "Deprecated key step_3_2.%s detected; ignored. "
                "Using fixed time columns %s/%s/%s.",
                legacy_key,
                CANONICAL_TIME_EVENTS_COLUMN,
                CANONICAL_TIME_RATE_COLUMN,
                CANONICAL_TIME_DURATION_COLUMN,
            )

    time_events_col: str | None = CANONICAL_TIME_EVENTS_COLUMN
    if time_events_col not in time_df.columns:
        log.warning(
            "Time series column '%s' not found; STEP 3.2 event filtering by target events is disabled.",
            time_events_col,
        )
        time_events_col = None

    time_rate_col: str | None = CANONICAL_TIME_RATE_COLUMN
    if time_rate_col not in time_df.columns:
        fallback = CANONICAL_TIME_RATE_FALLBACK_COLUMN
        if fallback in time_df.columns:
            time_rate_col = fallback
        else:
            log.warning(
                "No time-series rate column found (%s / %s); STEP 3.2 global rate will come from weighted feature space.",
                CANONICAL_TIME_RATE_COLUMN,
                fallback,
            )
            time_rate_col = None

    time_duration_col = CANONICAL_TIME_DURATION_COLUMN
    if time_duration_col not in time_df.columns:
        log.error("Time series duration column '%s' not found.", time_duration_col)
        return 1

    basis_events_col_cfg = str(cfg_32.get("basis_n_events_column", "n_events"))
    basis_events_col, basis_events_col_mode = _resolve_basis_events_column(
        basis_input_df,
        basis_events_col_cfg,
    )
    if basis_events_col_mode == "fallback":
        log.info(
            "Basis events column '%s' not usable in selected basis; using fallback '%s'.",
            basis_events_col_cfg,
            basis_events_col,
        )
    elif basis_events_col_mode == "configured_non_numeric":
        log.warning(
            "Basis events column '%s' has no finite numeric values; event filtering disabled.",
            basis_events_col_cfg,
        )
    basis_events_tol_pct = _safe_float(
        cfg_32.get("basis_n_events_tolerance_pct", cfg_32.get("basis_n_events_tolerance", 30.0)),
        30.0,
    )
    basis_parameter_set_col_cfg = cfg_32.get("basis_parameter_set_column", None)
    basis_min_rows = _safe_int(cfg_32.get("basis_min_rows", 200), 200, minimum=1)
    basis_event_filter_mode = _normalize_basis_event_filter_mode(
        cfg_32.get("basis_event_filter_mode", "event_tolerance")
    )

    basis_param_all = (
        basis_input_df[parameter_space_cols]
        .apply(pd.to_numeric, errors="coerce")
        .to_numpy(dtype=float)
    )
    basis_events_all = None
    if basis_events_col is not None and basis_events_col in basis_input_df.columns:
        basis_events_all = pd.to_numeric(basis_input_df[basis_events_col], errors="coerce").to_numpy(dtype=float)
    else:
        log.warning(
            "No usable basis events column found in selected basis; event filtering disabled. "
            "Configured: '%s'.",
            basis_events_col_cfg,
        )

    target_param_matrix = (
        time_df[parameter_space_cols]
        .apply(pd.to_numeric, errors="coerce")
        .to_numpy(dtype=float)
    )
    target_events = None
    if time_events_col is not None and time_events_col in time_df.columns:
        target_events = pd.to_numeric(time_df[time_events_col], errors="coerce").to_numpy(dtype=float)

    valid_basis = np.all(np.isfinite(basis_param_all), axis=1)
    valid_target = np.all(np.isfinite(target_param_matrix), axis=1)
    if not np.any(valid_basis):
        log.error(
            "No valid basis points in parameter space columns: %s",
            parameter_space_cols,
        )
        return 1
    if not np.all(valid_target):
        invalid_rows = int(np.sum(~valid_target))
        log.error(
            "Time series has %d invalid target row(s) in parameter space columns: %s",
            invalid_rows,
            parameter_space_cols,
        )
        return 1

    dictionary_work = basis_input_df.loc[valid_basis].reset_index(drop=True)
    basis_param_matrix = basis_param_all[valid_basis]
    basis_flux = (
        pd.to_numeric(dictionary_work[flux_col], errors="coerce").to_numpy(dtype=float)
        if flux_col is not None and flux_col in dictionary_work.columns
        else np.full(len(dictionary_work), np.nan, dtype=float)
    )
    basis_eff = (
        pd.to_numeric(dictionary_work[eff_col_basis], errors="coerce").to_numpy(dtype=float)
        if eff_col_basis is not None and eff_col_basis in dictionary_work.columns
        else np.full(len(dictionary_work), np.nan, dtype=float)
    )
    target_flux = (
        pd.to_numeric(time_df[flux_col], errors="coerce").to_numpy(dtype=float)
        if flux_col is not None and flux_col in time_df.columns
        else np.full(len(time_df), np.nan, dtype=float)
    )
    target_eff = (
        pd.to_numeric(time_df[eff_col_time], errors="coerce").to_numpy(dtype=float)
        if eff_col_time is not None and eff_col_time in time_df.columns
        else np.full(len(time_df), np.nan, dtype=float)
    )
    basis_events = None if basis_events_all is None else basis_events_all[valid_basis]
    basis_parameter_set_col = _select_parameter_set_column(dictionary_work, basis_parameter_set_col_cfg)
    if basis_parameter_set_col is None:
        log.warning(
            "No parameter-set column found in basis; each row will be treated as its own parameter set."
        )
        parameter_set_values = np.asarray([f"row_{i}" for i in range(len(dictionary_work))], dtype=object)
    else:
        parameter_set_values = dictionary_work[basis_parameter_set_col].astype(str).to_numpy(dtype=object)

    one_per_set_mask, one_per_set_info = _build_one_per_parameter_set_mask(
        parameter_set_values=parameter_set_values,
        basis_events=basis_events,
        target_events=target_events,
        basis_param_matrix=basis_param_matrix,
        target_param_matrix=target_param_matrix,
    )

    # Enforce one-row-per-parameter-set, then apply optional event-count tolerance.
    event_mask_extra, extra_info = _build_event_mask(
        basis_events=basis_events,
        target_events=target_events,
        tolerance_pct=basis_events_tol_pct,
        min_rows=basis_min_rows,
        filter_mode=basis_event_filter_mode,
        basis_param_matrix=basis_param_matrix,
        target_param_matrix=target_param_matrix,
    )
    if event_mask_extra is None:
        event_mask = one_per_set_mask
    else:
        event_mask = one_per_set_mask & event_mask_extra

    sel_counts = np.sum(event_mask, axis=1) if event_mask.size else np.array([], dtype=int)
    basis_filter_info = {
        "mode": "one_row_per_parameter_set_with_optional_event_tolerance",
        "parameter_set_mode": one_per_set_info.get("mode"),
        "n_parameter_sets": int(one_per_set_info.get("n_parameter_sets", 0)),
        "parameter_set_column": basis_parameter_set_col if basis_parameter_set_col is not None else "__row_index__",
        "basis_n_events_tolerance_pct_config": float(basis_events_tol_pct),
        "basis_min_rows_config": int(basis_min_rows),
        "basis_event_filter_mode_config": basis_event_filter_mode,
        "event_tolerance_filter_info": extra_info,
        "allowed_rows_per_target_min": int(np.min(sel_counts)) if sel_counts.size else 0,
        "allowed_rows_per_target_median": float(np.median(sel_counts)) if sel_counts.size else 0.0,
        "allowed_rows_per_target_max": int(np.max(sel_counts)) if sel_counts.size else 0,
        "targets_with_zero_selected_rows": int(np.sum(sel_counts <= 0)) if sel_counts.size else 0,
    }
    log.info(
        "Basis source=%s rows=%d (valid_parameter_rows=%d; dims=%d), one-per-set=%s(%s), tol_pct=%.3f -> selected/point min=%.0f med=%.1f max=%.0f (zero=%d).",
        basis_source,
        int(len(basis_input_df)),
        int(len(dictionary_work)),
        int(basis_param_matrix.shape[1]),
        str(one_per_set_info.get("mode", "n/a")),
        str(basis_filter_info.get("parameter_set_column")),
        float(basis_events_tol_pct),
        float(basis_filter_info.get("allowed_rows_per_target_min", len(dictionary_work))),
        float(basis_filter_info.get("allowed_rows_per_target_median", len(dictionary_work))),
        float(basis_filter_info.get("allowed_rows_per_target_max", len(dictionary_work))),
        int(basis_filter_info.get("targets_with_zero_selected_rows", 0)),
    )
    (
        tt_rate_consistency_cols,
        tt_rate_consistency_prefix,
        tt_rate_consistency_triggers,
    ) = _resolve_tt_rate_columns_for_consistency(dictionary_work)
    hist_rate_consistency_cols = _collect_histogram_rate_columns(dictionary_work)
    log.info(
        "Synthetic rate consistency: tt_prefix=%s tt_cols=%d hist_bin_cols=%d.",
        str(tt_rate_consistency_prefix),
        int(len(tt_rate_consistency_cols)),
        int(len(hist_rate_consistency_cols)),
    )

    interpolation_aggregation = _normalize_interpolation_aggregation(
        cfg_32.get("interpolation_aggregation", "local_linear")
    )
    if step31_curve_data_mode == "dataset_data_curve":
        feature_generation_mode = "dataset_data_curve"
    elif step31_mode_explicit:
        feature_generation_mode = "synthetic_data_curve"
    else:
        feature_generation_mode = "closest_point" if method == "closest_point" else "weighted_interpolation"
    show_diagnostic_center = _safe_bool(cfg_32.get("show_diagnostic_center", False), False)
    top_k_raw = cfg_32.get("top_k", None)
    top_k = None if top_k_raw in (None, "", 0) else _safe_int(top_k_raw, 8, minimum=1)
    distance_hardness = _safe_float(cfg_32.get("distance_hardness", 2.0), 2.0)
    enforce_distance_monotonic_weights = _safe_bool(
        cfg_32.get("enforce_distance_monotonic_weights", False),
        False,
    )
    density_enabled = _safe_bool(cfg_32.get("density_correction_enabled", False), False)
    density_k = _safe_int(cfg_32.get("density_correction_k_neighbors", 10), 10, minimum=1)
    if method in {"inverse_distance", "nearest", "closest_point", "softmax"} and density_enabled:
        log.info("Ignoring density correction for weighting_method=%s to match STEP 2 weighting behavior.", method)
        density_enabled = False
    if feature_generation_mode == "dataset_data_curve":
        density_enabled = False
    log.info(
        "Interpolation config: weighting_method=%s, generation_mode=%s, aggregation=%s, top_k=%s, weight_power=%.3g, show_diagnostic_center=%s",
        method,
        feature_generation_mode,
        interpolation_aggregation,
        ("all" if top_k is None else str(top_k)),
        float(distance_hardness),
        str(show_diagnostic_center).lower(),
    )
    for legacy_key in (
        "density_correction_space",
        "density_correction_exponent",
        "density_correction_clip_min",
        "density_correction_clip_max",
    ):
        if cfg_32.get(legacy_key) is not None:
            log.warning(
                "Deprecated key step_3_2.%s detected; ignored. "
                "Using fixed density exponent/clip constants.",
                legacy_key,
            )
    density_scaling = None
    density_info = {"enabled": bool(density_enabled)}
    if feature_generation_mode == "dataset_data_curve":
        selected_basis_positions = _resolve_step31_dataset_curve_basis_positions(
            time_df=time_df,
            basis_df=basis_input_df,
            valid_basis_mask=valid_basis,
        )
        weights = np.zeros((len(time_df), len(dictionary_work)), dtype=float)
        weights[np.arange(len(time_df), dtype=int), selected_basis_positions] = 1.0
        event_mask = weights > 0.0
        basis_filter_info = {
            "mode": "step31_dataset_curve_exact_rows",
            "parameter_set_mode": "step31_exact_source_rows",
            "n_parameter_sets": int(len(dictionary_work)),
            "parameter_set_column": basis_parameter_set_col if basis_parameter_set_col is not None else "__row_index__",
            "basis_n_events_tolerance_pct_config": float(basis_events_tol_pct),
            "basis_min_rows_config": int(basis_min_rows),
            "basis_event_filter_mode_config": basis_event_filter_mode,
            "event_tolerance_filter_info": {
                "mode": "bypassed_by_step31_dataset_curve",
            },
            "allowed_rows_per_target_min": 1,
            "allowed_rows_per_target_median": 1.0,
            "allowed_rows_per_target_max": 1,
            "targets_with_zero_selected_rows": 0,
        }
        density_info = {
            "enabled": False,
            "bypassed_by_step31_dataset_curve": True,
        }
        log.info(
            "STEP 3.2 exact-row mode: one source dataset row per target, resolved directly from STEP 3.1."
        )
    elif density_enabled:
        density_scaling, density_info = _compute_inverse_density_scaling(
            basis_param_matrix=basis_param_matrix,
            k_neighbors=density_k,
            exponent=CANONICAL_DENSITY_EXPONENT,
            clip_min=CANONICAL_DENSITY_CLIP_MIN,
            clip_max=CANONICAL_DENSITY_CLIP_MAX,
        )
        weights = _build_weights(
            dict_param_matrix=basis_param_matrix,
            target_param_matrix=target_param_matrix,
            method=method,
            top_k=top_k,
            distance_hardness=distance_hardness,
            density_scaling=density_scaling,
            event_mask=event_mask,
            enforce_distance_monotonic_weights=enforce_distance_monotonic_weights,
        )
    else:
        weights = _build_weights(
            dict_param_matrix=basis_param_matrix,
            target_param_matrix=target_param_matrix,
            method=method,
            top_k=top_k,
            distance_hardness=distance_hardness,
            density_scaling=density_scaling,
            event_mask=event_mask,
            enforce_distance_monotonic_weights=enforce_distance_monotonic_weights,
        )
    # Diagnostic center in parameter space: weighted by the same basis weights
    # used for synthetic-column generation (includes density modulation when enabled).
    diagnostic_columns: list[str] = []
    for col in [*parameter_space_cols, flux_col, eff_col_basis]:
        if not isinstance(col, str) or not col:
            continue
        if col in dictionary_work.columns and col not in diagnostic_columns:
            diagnostic_columns.append(col)
    diagnostic_center_values = _weighted_numeric_columns(
        weights=weights,
        dict_df=dictionary_work,
        columns=diagnostic_columns,
        interpolation_aggregation=interpolation_aggregation,
        basis_param_matrix=basis_param_matrix,
        target_param_matrix=target_param_matrix,
    )
    diagnostic_flux = np.asarray(
        diagnostic_center_values.get(
            flux_col,
            np.full(len(time_df), np.nan, dtype=float),
        ) if isinstance(flux_col, str) and flux_col else np.full(len(time_df), np.nan, dtype=float),
        dtype=float,
    )
    diagnostic_eff = np.asarray(
        diagnostic_center_values.get(
            eff_col_basis,
            np.full(len(time_df), np.nan, dtype=float),
        ) if isinstance(eff_col_basis, str) and eff_col_basis else np.full(len(time_df), np.nan, dtype=float),
        dtype=float,
    )
    diagnostic_param_mae: dict[str, float | None] = {}
    for col_idx, col_name in enumerate(parameter_space_cols):
        center_col = np.asarray(
            diagnostic_center_values.get(col_name, np.full(len(time_df), np.nan, dtype=float)),
            dtype=float,
        )
        target_col = np.asarray(target_param_matrix[:, col_idx], dtype=float)
        m_col = np.isfinite(center_col) & np.isfinite(target_col)
        diagnostic_param_mae[col_name] = (
            float(np.mean(np.abs(center_col[m_col] - target_col[m_col])))
            if np.any(m_col)
            else None
        )
    center_prefix = "Density-modulated " if density_enabled else ""
    if feature_generation_mode == "dataset_data_curve":
        diagnostic_center_label = "Exact STEP 3.1 dataset-backed row"
    elif interpolation_aggregation == "local_linear":
        diagnostic_center_label = f"{center_prefix}local-linear parameter-space center (diagnostic)"
    else:
        diagnostic_center_label = f"{center_prefix}weighted parameter-space center (diagnostic)"
    diagnostic_flux_mae = diagnostic_param_mae.get(flux_col) if flux_col is not None else None
    diagnostic_eff_mae = diagnostic_param_mae.get(eff_col_time) if eff_col_time is not None else None
    flux_label = flux_col if flux_col is not None else "no_flux_axis"
    eff_label = eff_col_time if eff_col_time is not None else "no_eff_axis"
    log.info(
        "Diagnostic center check: %s MAE=%.6g, %s MAE=%.6g.",
        flux_label,
        float(diagnostic_flux_mae) if diagnostic_flux_mae is not None else float("nan"),
        eff_label,
        float(diagnostic_eff_mae) if diagnostic_eff_mae is not None else float("nan"),
    )

    # Flux/eff assigned to synthetic rows: fixed to STEP 3.1 discretized target.
    flux_linear = target_flux.copy() if flux_col is not None else None
    eff_linear = target_eff.copy() if eff_col_time is not None else None

    synthetic_df, dominant_idx = _make_synthetic_dataset(
        dictionary_df=dictionary_work,
        template_df=template_df,
        time_df=time_df,
        weights=weights,
        basis_param_matrix=basis_param_matrix,
        target_param_matrix=target_param_matrix,
        feature_generation_mode=feature_generation_mode,
        flux_col=flux_col,
        eff_col=eff_col_time,
        time_rate_col=time_rate_col,
        time_events_col=time_events_col,
        time_duration_col=time_duration_col,
        interpolation_aggregation=interpolation_aggregation,
        flux_output_values=flux_linear,
        eff_output_values=eff_linear,
        tt_rate_columns_for_consistency=tt_rate_consistency_cols,
        histogram_rate_columns_for_consistency=hist_rate_consistency_cols,
    )
    if feature_generation_mode == "closest_point":
        for col in parameter_space_cols:
            if col in time_df.columns:
                synthetic_df[f"step32_target_{col}"] = pd.to_numeric(
                    time_df[col],
                    errors="coerce",
                ).to_numpy(dtype=float)
    elif feature_generation_mode in {"weighted_interpolation", "synthetic_data_curve"}:
        # Keep parameter-space coordinates exactly equal to STEP 3.1 targets.
        for col in parameter_space_cols:
            if col in synthetic_df.columns and col in time_df.columns:
                synthetic_df[col] = pd.to_numeric(time_df[col], errors="coerce").to_numpy(dtype=float)
        helper_rebuild_info = _rebuild_weighted_step12_helper_columns(synthetic_df)
        _rebuild_efficiencies_string(synthetic_df)
        if bool(helper_rebuild_info.get("applied")):
            log.info(
                "Rebuilt weighted STEP 1.2 helper columns after target-parameter override: "
                "synced_eff_alias=%d products=%d proxies=%d",
                int(len(helper_rebuild_info.get("synced_eff_alias_columns", []))),
                int(len(helper_rebuild_info.get("rebuilt_efficiency_product_columns", []))),
                int(len(helper_rebuild_info.get("rebuilt_flux_proxy_columns", []))),
            )
    else:
        helper_rebuild_info = {"applied": False}
    if feature_generation_mode == "closest_point":
        helper_rebuild_info = {"applied": False}

    rate_consistency_info = dict(synthetic_df.attrs.get("rate_consistency_info", {}))
    rate_consistency_info["tt_prefix_selected"] = tt_rate_consistency_prefix
    rate_consistency_info["tt_trigger_types_selected"] = tt_rate_consistency_triggers
    rate_consistency_info["tt_columns_selected"] = tt_rate_consistency_cols

    # Output files
    out_synth = FILES_DIR / "synthetic_dataset.csv"
    synthetic_df.to_csv(out_synth, index=False)
    log.info("Wrote synthetic dataset: %s (%d rows)", out_synth, len(synthetic_df))

    # Persist the exact STEP 3.2 diagnostic center series so downstream steps
    # (e.g. STEP 3.3 plots) can reuse it directly without recomputation.
    center_df = pd.DataFrame({
        "row_index": np.arange(len(time_df), dtype=int),
        "file_index": pd.to_numeric(time_df.get("file_index"), errors="coerce").astype("Int64"),
        "elapsed_hours": pd.to_numeric(time_df.get("elapsed_hours"), errors="coerce"),
        "center_flux_cm2_min": np.asarray(diagnostic_flux, dtype=float),
        "center_eff": np.asarray(diagnostic_eff, dtype=float),
        "eff_column_used": eff_col_time,
        "center_label": diagnostic_center_label,
        "interpolation_aggregation": interpolation_aggregation,
    }, index=time_df.index).reset_index(drop=True)
    out_center = FILES_DIR / "diagnostic_center_series.csv"
    center_df.to_csv(out_center, index=False)
    log.info("Wrote diagnostic center series: %s", out_center)

    # Highlight point for contribution diagnostics
    seed_cfg = cfg_32.get("random_seed", None)
    if seed_cfg in (None, "", "null", "None"):
        rng = np.random.default_rng()
        seed_used: int | None = None
    else:
        seed_used = _safe_int(seed_cfg, 0)
        rng = np.random.default_rng(seed_used)
    highlight_cfg = cfg_32.get("highlight_point_index", None)
    if highlight_cfg is None:
        highlight_idx = int(rng.integers(0, len(time_df)))
    else:
        highlight_idx = int(np.clip(_safe_int(highlight_cfg, 0), 0, len(time_df) - 1))

    contrib = weights[highlight_idx]
    event_allowed_highlight = np.asarray(event_mask[highlight_idx], dtype=bool)
    highlight_target_param_matrix = target_param_matrix[highlight_idx:highlight_idx + 1, :]
    distance_sigma = np.sqrt(
        _pairwise_standardized_squared_distances(
            dict_param_matrix=basis_param_matrix,
            target_param_matrix=highlight_target_param_matrix,
        )[0]
    )

    distance_rank_all = np.full(len(contrib), np.nan, dtype=float)
    finite_dist = np.isfinite(distance_sigma)
    if np.any(finite_dist):
        idx_all = np.where(finite_dist)[0]
        ord_all = np.argsort(distance_sigma[idx_all], kind="mergesort")
        distance_rank_all[idx_all[ord_all]] = np.arange(1, len(idx_all) + 1, dtype=float)

    distance_rank_event_allowed = np.full(len(contrib), np.nan, dtype=float)
    finite_allowed = finite_dist & event_allowed_highlight
    if np.any(finite_allowed):
        idx_allowed = np.where(finite_allowed)[0]
        ord_allowed = np.argsort(distance_sigma[idx_allowed], kind="mergesort")
        distance_rank_event_allowed[idx_allowed[ord_allowed]] = np.arange(1, len(idx_allowed) + 1, dtype=float)

    def _nearest_idx(mask: np.ndarray) -> int | None:
        if not np.any(mask):
            return None
        cand = np.where(mask, distance_sigma, np.inf)
        if not np.isfinite(cand).any():
            return None
        return int(np.argmin(cand))

    nearest_any_idx = _nearest_idx(finite_dist)
    nearest_allowed_idx = _nearest_idx(finite_allowed)
    top_weight_idx = int(np.argmax(contrib)) if contrib.size else None

    pos = (contrib > 0.0) & np.isfinite(distance_sigma)
    monotonic_inversions = 0
    monotonic_pairs = 0
    if np.count_nonzero(pos) >= 2:
        pos_idx = np.where(pos)[0]
        ord_pos = np.argsort(distance_sigma[pos_idx], kind="mergesort")
        w_sorted = contrib[pos_idx][ord_pos]
        monotonic_pairs = max(len(w_sorted) - 1, 0)
        monotonic_inversions = int(np.sum(w_sorted[1:] > (w_sorted[:-1] + 1e-15)))

    contrib_df = pd.DataFrame({
        "rank": np.arange(1, len(contrib) + 1),
        "basis_index": np.arange(len(contrib)),
        "dictionary_index": np.arange(len(contrib)),
        "distance_parameter_space": distance_sigma,
        "distance_sigma": distance_sigma,
        "distance_rank_all": distance_rank_all,
        "distance_rank_event_allowed": distance_rank_event_allowed,
        "weight": contrib,
        "weight_pct": contrib * 100.0,
        "is_event_allowed": event_allowed_highlight,
        "is_weight_positive": contrib > 0.0,
        "basis_source": basis_source,
    })
    if flux_col is not None:
        contrib_df[flux_col] = basis_flux
    if eff_col_basis is not None:
        contrib_df[eff_col_basis] = basis_eff
    for col in parameter_space_cols:
        if col in contrib_df.columns or col not in dictionary_work.columns:
            continue
        contrib_df[col] = pd.to_numeric(dictionary_work[col], errors="coerce")
    if basis_parameter_set_col is not None and basis_parameter_set_col in dictionary_work.columns:
        contrib_df["basis_parameter_set_id"] = dictionary_work[basis_parameter_set_col].astype(str)
    if "filename_base" in dictionary_work.columns:
        contrib_df["filename_base"] = dictionary_work["filename_base"].astype(str)
    if "events_per_second_global_rate" in dictionary_work.columns:
        contrib_df["events_per_second_global_rate"] = pd.to_numeric(
            dictionary_work["events_per_second_global_rate"], errors="coerce"
        )
    contrib_df = contrib_df.sort_values(["weight", "distance_sigma"], ascending=[False, True]).reset_index(drop=True)
    contrib_df["rank"] = np.arange(1, len(contrib_df) + 1)
    for col in ("distance_rank_all", "distance_rank_event_allowed"):
        contrib_df[col] = pd.to_numeric(contrib_df[col], errors="coerce").round().astype("Int64")

    out_contrib = FILES_DIR / "highlight_point_contributions.csv"
    contrib_df.to_csv(out_contrib, index=False)
    log.info("Wrote highlight contributions: %s", out_contrib)

    # Plots
    out_plot_contrib = PLOTS_DIR / "dictionary_contributions_highlight.png"
    _plot_highlight_contributions(
        complete_df=complete_df,
        time_df=time_df,
        dictionary_df=dictionary_work,
        weights=weights,
        event_allowed_mask=event_allowed_highlight,
        basis_label=basis_label,
        highlight_idx=highlight_idx,
        parameter_space_cols=parameter_space_cols,
        path=out_plot_contrib,
    )
    log.info("Wrote plot: %s", out_plot_contrib)

    out_plot_series = PLOTS_DIR / "synthetic_time_series_overview.png"
    _plot_time_series_overview(
        complete_df=complete_df,
        time_df=time_df,
        synthetic_df=synthetic_df,
        flux_col=flux_col,
        eff_col=eff_col_time,
        time_rate_col=time_rate_col,
        interpolated_flux=diagnostic_flux,
        interpolated_eff=diagnostic_eff,
        interpolated_label=diagnostic_center_label,
        show_diagnostic_center=show_diagnostic_center,
        path=out_plot_series,
    )
    log.info("Wrote plot: %s", out_plot_series)

    out_plot_paramspace = PLOTS_DIR / "parameter_space_lower_triangle.png"
    _plot_parameter_space_lower_triangle(
        basis_df=dictionary_work,
        time_df=time_df,
        synthetic_df=synthetic_df,
        complete_df=complete_df,
        parameter_space_cols=parameter_space_cols,
        path=out_plot_paramspace,
    )
    log.info("Wrote plot: %s", out_plot_paramspace)

    # Histogram: full dataset events vs selected basis subset events (same bins).
    if basis_events_col in template_df.columns:
        dataset_events_all = pd.to_numeric(template_df[basis_events_col], errors="coerce").to_numpy(dtype=float)
    else:
        dataset_events_all = np.array([], dtype=float)
    basis_selected_any = np.any(event_mask, axis=0)
    basis_subset_events = (
        np.asarray(basis_events, dtype=float)[basis_selected_any]
        if basis_events is not None and len(basis_events) == event_mask.shape[1]
        else np.array([], dtype=float)
    )
    basis_subset_events_finite = basis_subset_events[np.isfinite(basis_subset_events)]
    out_plot_events_hist = PLOTS_DIR / "events_count_dataset_vs_basis_subset.png"
    _plot_events_count_histogram(
        dataset_events=dataset_events_all,
        basis_subset_events=basis_subset_events,
        path=out_plot_events_hist,
    )
    log.info("Wrote plot: %s", out_plot_events_hist)

    feature_space_plot_info = _resolve_feature_space_plot_columns(
        dictionary_work,
        synthetic_df,
        selected_features_path=selected_features_path,
        suppressed_patterns=feature_space_plot_suppressed_patterns,
        histogram_sample_count=feature_plot_histogram_sample_count,
        max_efficiency_groups=feature_plot_max_efficiency_groups,
        max_other_columns=feature_plot_max_other_columns,
    )
    out_plot_feature_space = PLOTS_DIR / "feature_space_lower_triangle.png"
    if feature_space_plot_info["columns_used"]:
        saved_feature_space_plot_path = _plot_feature_space_lower_triangle(
            basis_df=dictionary_work,
            synthetic_df=synthetic_df,
            feature_cols=list(feature_space_plot_info["columns_used"]),
            feature_labels=dict(feature_space_plot_info["column_display_labels"]),
            rate_hist_count=int(feature_space_plot_info["histogram_columns_available_count"]),
            efficiency_vector_count=int(feature_space_plot_info["efficiency_vector_columns_available_count"]),
            path=out_plot_feature_space,
        )
        feature_space_plot_info["path"] = str(saved_feature_space_plot_path or out_plot_feature_space)
        feature_space_plot_info["status"] = "ok"
        log.info(
            "Wrote plot: %s (feature-space representative columns=%d)",
            feature_space_plot_info["path"],
            int(len(feature_space_plot_info["columns_used"])),
        )
    else:
        feature_space_plot_info["path"] = str(out_plot_feature_space)
        feature_space_plot_info["status"] = "skipped_no_common_feature_columns"
        log.warning(
            "Skipped STEP 3.2 feature-space lower triangle: no common selected feature columns found "
            "between dictionary and synthetic dataset."
        )

    # Summary
    effective_n = 1.0 / np.sum(weights * weights, axis=1)
    summary = {
        "time_series_csv": str(time_series_path),
        "complete_curve_csv": str(complete_curve_path if complete_curve_path.exists() else ""),
        "dictionary_csv": str(dictionary_path),
        "dataset_template_csv": str(template_path),
        "parameter_space_spec_json": str(DEFAULT_PARAMETER_SPACE_SPEC),
        "parameter_space_alias_columns_added_time_series": time_alias_cols,
        "parameter_space_alias_columns_added_dictionary": dictionary_alias_cols,
        "parameter_space_alias_columns_added_dataset_template": template_alias_cols,
        "parameter_space_alias_columns_added_complete_curve": complete_alias_cols,
        "basis_source": basis_source,
        "basis_csv": str(basis_path),
        "selected_feature_columns_json": str(selected_features_path),
        "flux_column_used": flux_col,
        "efficiency_column_requested": eff_pref,
        "efficiency_column_used_time": eff_col_time,
        "efficiency_column_used_basis": eff_col_basis,
        "parameter_space_columns_config": parameter_space_cfg,
        "parameter_space_columns_used_for_weighting": parameter_space_cols,
        "parameter_space_dimensions": int(len(parameter_space_cols)),
        "basis_events_column_configured": basis_events_col_cfg,
        "basis_events_column_used": basis_events_col,
        "basis_events_column_resolution": basis_events_col_mode,
        "basis_events_filter": basis_filter_info,
        "basis_event_filter_mode": basis_event_filter_mode,
        "step31_curve_data_mode": step31_curve_data_mode,
        "step31_curve_data_mode_explicit": bool(step31_mode_explicit),
        "feature_generation_mode": feature_generation_mode,
        "flux_eff_assignment_method": (
            "copied_from_step31_dataset_curve_row"
            if feature_generation_mode == "dataset_data_curve"
            else "copied_from_closest_basis_row"
            if feature_generation_mode == "closest_point"
            else "target_discretized_from_step_3_1"
        ),
        "global_rate_assignment_method": (
            "copied_from_step31_dataset_curve_row"
            if feature_generation_mode == "dataset_data_curve"
            else "copied_from_closest_basis_row"
            if feature_generation_mode == "closest_point"
            else "weighted_feature_space_from_step_3_2"
        ),
        "diagnostic_center_method": (
            "exact_step31_dataset_row"
            if feature_generation_mode == "dataset_data_curve"
            else "weighted_parameter_space_center_not_used_for_output"
        ),
        "diagnostic_flux_eff_center_label": diagnostic_center_label,
        "diagnostic_parameter_mae_vs_target": diagnostic_param_mae,
        "diagnostic_flux_center_mae_vs_target": diagnostic_flux_mae,
        "diagnostic_eff_center_mae_vs_target": diagnostic_eff_mae,
        "diagnostic_flux_center_range": [
            float(np.nanmin(diagnostic_flux)) if np.isfinite(diagnostic_flux).any() else None,
            float(np.nanmax(diagnostic_flux)) if np.isfinite(diagnostic_flux).any() else None,
        ],
        "diagnostic_eff_center_range": [
            float(np.nanmin(diagnostic_eff)) if np.isfinite(diagnostic_eff).any() else None,
            float(np.nanmax(diagnostic_eff)) if np.isfinite(diagnostic_eff).any() else None,
        ],
        "density_correction": density_info,
        "basis_subset_unique_rows_count": int(np.sum(basis_selected_any)),
        "basis_subset_unique_events_min": float(np.min(basis_subset_events_finite)) if basis_subset_events_finite.size else None,
        "basis_subset_unique_events_max": float(np.max(basis_subset_events_finite)) if basis_subset_events_finite.size else None,
        "basis_subset_unique_events_median": float(np.median(basis_subset_events_finite)) if basis_subset_events_finite.size else None,
        "n_time_points": int(len(time_df)),
        "n_basis_points": int(len(dictionary_work)),
        "n_dictionary_points": int(len(dictionary_work)),
        "n_synthetic_rows": int(len(synthetic_df)),
        "weighting_method": (
            "step31_dataset_curve_exact_copy"
            if feature_generation_mode == "dataset_data_curve"
            else method
        ),
        "interpolation_aggregation": interpolation_aggregation,
        "distance_definition": "standardized_euclidean_in_parameter_space",
        "distance_hardness": float(distance_hardness),
        "step2_style_weight_power": float(distance_hardness) if method in {"inverse_distance", "softmax"} else None,
        "enforce_distance_monotonic_weights": bool(enforce_distance_monotonic_weights),
        "top_k": int(top_k) if top_k is not None else None,
        "highlight_point_index": int(highlight_idx),
        "highlight_random_seed": seed_used,
        "highlight_nearest_any_basis_index": nearest_any_idx,
        "highlight_nearest_any_distance_sigma": (
            float(distance_sigma[nearest_any_idx]) if nearest_any_idx is not None else None
        ),
        "highlight_nearest_any_event_allowed": (
            bool(event_allowed_highlight[nearest_any_idx]) if nearest_any_idx is not None else None
        ),
        "highlight_nearest_allowed_basis_index": nearest_allowed_idx,
        "highlight_nearest_allowed_distance_sigma": (
            float(distance_sigma[nearest_allowed_idx]) if nearest_allowed_idx is not None else None
        ),
        "highlight_top_weight_basis_index": top_weight_idx,
        "highlight_top_weight_distance_sigma": (
            float(distance_sigma[top_weight_idx]) if top_weight_idx is not None else None
        ),
        "highlight_top_weight_pct": (
            float(contrib[top_weight_idx] * 100.0) if top_weight_idx is not None else None
        ),
        "highlight_nonzero_adjacent_monotonic_inversions": int(monotonic_inversions),
        "highlight_nonzero_adjacent_monotonic_pairs": int(monotonic_pairs),
        "highlight_nonzero_adjacent_monotonic_inversion_rate": (
            float(monotonic_inversions / monotonic_pairs) if monotonic_pairs > 0 else 0.0
        ),
        "median_effective_contributors": float(np.nanmedian(effective_n)),
        "min_effective_contributors": float(np.nanmin(effective_n)),
        "max_effective_contributors": float(np.nanmax(effective_n)),
        "dominant_basis_unique_count": int(len(np.unique(dominant_idx))),
        "dominant_dictionary_unique_count": int(len(np.unique(dominant_idx))),
        "synthetic_flux_range": [
            float(pd.to_numeric(synthetic_df.get("flux_cm2_min"), errors="coerce").min()),
            float(pd.to_numeric(synthetic_df.get("flux_cm2_min"), errors="coerce").max()),
        ],
        "synthetic_eff_range": [
            float(pd.to_numeric(synthetic_df.get("eff_sim_1"), errors="coerce").min()),
            float(pd.to_numeric(synthetic_df.get("eff_sim_1"), errors="coerce").max()),
        ],
        "synthetic_global_rate_range_hz": [
            float(pd.to_numeric(synthetic_df.get("events_per_second_global_rate"), errors="coerce").min()),
            float(pd.to_numeric(synthetic_df.get("events_per_second_global_rate"), errors="coerce").max()),
        ],
        "feature_space_lower_triangle_plot": feature_space_plot_info,
        "weighted_helper_rebuild": helper_rebuild_info,
        "rate_consistency_constraints": rate_consistency_info,
        "diagnostic_center_series_csv": str(out_center),
    }
    out_summary = FILES_DIR / "synthetic_generation_summary.json"
    with open(out_summary, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    log.info("Wrote summary: %s", out_summary)

    log.info("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
