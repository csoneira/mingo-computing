#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_SIMULATION/MINGO_DICTIONARY_CREATION_AND_TEST/STEPS/STEP_1_SETUP/STEP_1_2_TRANSFORM_FEATURE_SPACE/transform_feature_space.py
Purpose: STEP 1.2 — Transform expanded feature space from STEP 1.1.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-11
Runtime: python3
Usage: python3 PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_SIMULATION/MINGO_DICTIONARY_CREATION_AND_TEST/STEPS/STEP_1_SETUP/STEP_1_2_TRANSFORM_FEATURE_SPACE/transform_feature_space.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import json
import logging
import operator
import re
import sys
from pathlib import Path
from typing import Mapping, Sequence

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
DEFAULT_CONFIG = PIPELINE_DIR / "config_step_1.1_method.json"
MODULES_DIR = PIPELINE_DIR / "STEPS" / "MODULES" if (PIPELINE_DIR / "STEPS" / "MODULES").exists() else PIPELINE_DIR / "MODULES"
DEFAULT_INPUT = (
    STEP_DIR.parent / "STEP_1_1_COLLECT_DATA" / "OUTPUTS" / "FILES" / "collected_data.csv"
)
DEFAULT_STEP13_SELECTED_FEATURES = (
    STEP_DIR.parent / "STEP_1_3_BUILD_DICTIONARY" / "OUTPUTS" / "FILES" / "selected_feature_columns.json"
)
DEFAULT_STEP14_SELECTED_FEATURES = (
    STEP_DIR.parent / "STEP_1_4_ENSURE_CONTINUITY_DICTIONARY" / "OUTPUTS" / "FILES" / "selected_feature_columns.json"
)
DEFAULT_STEP11_PARAMETER_SPACE = (
    STEP_DIR.parent / "STEP_1_1_COLLECT_DATA" / "OUTPUTS" / "FILES" / "parameter_space_columns.json"
)
STEP2_INFERENCE_DIR = PIPELINE_DIR / "STEPS" / "STEP_2_INFERENCE"

FILES_DIR = STEP_DIR / "OUTPUTS" / "FILES"
PLOTS_DIR = STEP_DIR / "OUTPUTS" / "PLOTS"
FILES_DIR.mkdir(parents=True, exist_ok=True)
PLOTS_DIR.mkdir(parents=True, exist_ok=True)

_FIGURE_COUNTER = 0
FIGURE_STEP_PREFIX = "1_2"


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

CANONICAL_TT_LABELS = frozenset(
    {
        "0",
        "1",
        "2",
        "3",
        "4",
        "12",
        "13",
        "14",
        "23",
        "24",
        "34",
        "123",
        "124",
        "134",
        "234",
        "1234",
    }
)
TT_RATE_COLUMN_RE = re.compile(r"^(?P<prefix>.+_tt)_(?P<label>[^_]+)_rate_hz$")
HIST_RATE_COLUMN_RE = re.compile(r"^events_per_second_(?P<bin>\d+)_rate_hz$")
STANDARD_TASK_PREFIXES = ("raw_tt", "clean_tt", "cal_tt", "list_tt", "fit_tt", "post_tt")
CANONICAL_PREFIX_PRIORITY = (
    "post_tt",
    "fit_to_post_tt",
    "fit_tt",
    "list_to_fit_tt",
    "list_tt",
    "cal_tt",
    "clean_tt",
    "raw_to_clean_tt",
    "raw_tt",
    "corr_tt",
    "task5_to_corr_tt",
    "fit_to_corr_tt",
    "definitive_tt",
)

if str(MODULES_DIR) not in sys.path:
    sys.path.insert(0, str(MODULES_DIR))
if str(STEP2_INFERENCE_DIR) not in sys.path:
    sys.path.insert(0, str(STEP2_INFERENCE_DIR))
try:
    from feature_space_config import (  # noqa: E402
        extract_feature_dimensions,
        load_feature_space_config,
        resolve_feature_space_config_path,
        resolve_feature_space_transform_options,
        resolve_materialized_feature_space_columns,
        resolve_selected_feature_space_columns,
    )
except Exception as exc:  # pragma: no cover - import failure is fatal
    raise RuntimeError(f"Could not import feature_space_config from {MODULES_DIR}: {exc}") from exc
try:
    from estimate_parameters import (  # noqa: E402
        _filter_efficiency_vector_payloads,
        _prepare_efficiency_vector_group_payloads,
        load_distance_definition,
    )
except Exception as exc:  # pragma: no cover - import failure is fatal
    raise RuntimeError(f"Could not import estimate_parameters from {STEP2_INFERENCE_DIR}: {exc}") from exc
RATE_HIST_PLACEHOLDER_COL = "__RATE_HISTOGRAM_SUPPRESSED__"
RATE_HIST_PLACEHOLDER_LABEL = "events_per_second_<bin>_rate_hz [suppressed]"
EFF_PLACEHOLDER_COL = "__EFFICIENCY_VECTORS_SUPPRESSED__"
EFF_PLACEHOLDER_LABEL = "efficiency_vector_<axis>_bin_*_eff [suppressed]"
DEFAULT_FEATURE_SPACE_LOWER_TRIANGLE_SUPPRESSED_PATTERNS = (
    "events_per_second_*_rate_hz",
    "efficiency_vector_*",
)
DEFAULT_POST_TT_AGGREGATE_TWO_PLANE_LABELS = ("12", "13", "14", "23", "24", "34")
DEFAULT_POST_TT_AGGREGATE_THREE_PLANE_LABELS = ("123", "124", "134", "234")
DEFAULT_POST_TT_AGGREGATE_FOUR_PLANE_LABEL = "1234"
DEFAULT_DERIVED_COLUMNS_CATALOG: dict[str, dict[str, str]] = {
    "events_per_second_global_rate_{prefix}": {
        "source": "sum over available canonical trigger-type rates {prefix}_{label}_rate_hz",
        "generated_when": "always (built before column curation)",
    },
    "events_per_second_global_rate": {
        "source": "canonical pick from events_per_second_global_rate_{prefix} using tt_prefix_priority with fallback_existing_global_rate",
        "generated_when": "transformations.derive_canonical_global_rate",
    },
    "eff_empirical_1": {
        "source": "{prefix}_1234_rate_hz / ({prefix}_1234_rate_hz + {prefix}_234_rate_hz)",
        "generated_when": "transformations.derive_empirical_efficiencies",
    },
    "eff_empirical_2": {
        "source": "{prefix}_1234_rate_hz / ({prefix}_1234_rate_hz + {prefix}_134_rate_hz)",
        "generated_when": "transformations.derive_empirical_efficiencies",
    },
    "eff_empirical_3": {
        "source": "{prefix}_1234_rate_hz / ({prefix}_1234_rate_hz + {prefix}_124_rate_hz)",
        "generated_when": "transformations.derive_empirical_efficiencies",
    },
    "eff_empirical_4": {
        "source": "{prefix}_1234_rate_hz / ({prefix}_1234_rate_hz + {prefix}_123_rate_hz)",
        "generated_when": "transformations.derive_empirical_efficiencies",
    },
    "eff_empirical_source_prefix": {
        "source": "prefix used for each row's empirical-efficiency fill",
        "generated_when": "transformations.derive_empirical_efficiencies",
    },
    "post_tt_two_plane_total_rate_hz": {
        "source": "sum(post_tt_12_rate_hz, post_tt_13_rate_hz, post_tt_14_rate_hz, post_tt_23_rate_hz, post_tt_24_rate_hz, post_tt_34_rate_hz)",
        "generated_when": "transformations.derive_post_tt_plane_aggregates",
    },
    "post_tt_three_plane_total_rate_hz": {
        "source": "sum(post_tt_123_rate_hz, post_tt_124_rate_hz, post_tt_134_rate_hz, post_tt_234_rate_hz)",
        "generated_when": "transformations.derive_post_tt_plane_aggregates",
    },
    "post_tt_four_plane_rate_hz": {
        "source": "post_tt_1234_rate_hz",
        "generated_when": "transformations.derive_post_tt_plane_aggregates",
    },
    "efficiency_product_4planes": {
        "source": "eff_p1 * eff_p2 * eff_p3 * eff_p4",
        "generated_when": "transformations.derive_physics_helpers",
    },
    "efficiency_product_123": {
        "source": "eff_p1 * eff_p2 * eff_p3",
        "generated_when": "transformations.derive_physics_helpers",
    },
    "efficiency_product_234": {
        "source": "eff_p2 * eff_p3 * eff_p4",
        "generated_when": "transformations.derive_physics_helpers",
    },
    "efficiency_product_12": {
        "source": "eff_p1 * eff_p2",
        "generated_when": "transformations.derive_physics_helpers",
    },
    "efficiency_product_34": {
        "source": "eff_p3 * eff_p4",
        "generated_when": "transformations.derive_physics_helpers",
    },
    "flux_proxy_rate_div_effprod": {
        "source": "events_per_second_global_rate / efficiency_product_4planes",
        "generated_when": "transformations.derive_physics_helpers",
    },
    "flux_proxy_rate_div_effprod_123": {
        "source": "events_per_second_global_rate / efficiency_product_123",
        "generated_when": "transformations.derive_physics_helpers",
    },
    "flux_proxy_rate_div_effprod_234": {
        "source": "events_per_second_global_rate / efficiency_product_234",
        "generated_when": "transformations.derive_physics_helpers",
    },
    "flux_proxy_rate_div_effprod_12": {
        "source": "events_per_second_global_rate / efficiency_product_12",
        "generated_when": "transformations.derive_physics_helpers",
    },
    "flux_proxy_rate_div_effprod_34": {
        "source": "events_per_second_global_rate / efficiency_product_34",
        "generated_when": "transformations.derive_physics_helpers",
    },
}


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


logging.basicConfig(
    format="[%(levelname)s] STEP_1.2 — %(message)s", level=logging.INFO
)
log = logging.getLogger("STEP_1.2")


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


def _find_eff_source_columns(df: pd.DataFrame) -> list[str] | None:
    direct = ["eff_p1", "eff_p2", "eff_p3", "eff_p4"]
    if all(col in df.columns for col in direct):
        return direct
    parsed = ["eff_sim_1", "eff_sim_2", "eff_sim_3", "eff_sim_4"]
    if all(col in df.columns for col in parsed):
        return parsed
    return None


def _parse_efficiencies(raw: object) -> tuple[float, float, float, float] | None:
    value = raw
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
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


def _ensure_efficiency_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    source_cols = _find_eff_source_columns(out)
    if source_cols is not None and source_cols != ["eff_p1", "eff_p2", "eff_p3", "eff_p4"]:
        for idx, src in enumerate(source_cols, start=1):
            out[f"eff_p{idx}"] = pd.to_numeric(out[src], errors="coerce")
    elif source_cols is None and "efficiencies" in out.columns:
        parsed = out["efficiencies"].map(_parse_efficiencies)
        for idx in range(4):
            out[f"eff_p{idx + 1}"] = parsed.map(lambda v, j=idx: np.nan if v is None else float(v[j]))

    for idx in range(4):
        ep = f"eff_p{idx + 1}"
        es = f"eff_sim_{idx + 1}"
        if ep in out.columns and es not in out.columns:
            out[es] = pd.to_numeric(out[ep], errors="coerce")
    return out


def _build_prefix_global_rate_columns(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, str], dict[str, list[str]]]:
    by_prefix: dict[str, list[str]] = {}
    for col in df.columns:
        match = TT_RATE_COLUMN_RE.match(str(col))
        if match is None:
            continue
        prefix = str(match.group("prefix")).strip()
        label = _normalize_tt_label(match.group("label"))
        if label not in CANONICAL_TT_LABELS:
            continue
        by_prefix.setdefault(prefix, []).append(str(col))

    out = df.copy()
    rate_col_by_prefix: dict[str, str] = {}
    tt_cols_by_prefix: dict[str, list[str]] = {}
    for prefix in sorted(by_prefix):
        cols = sorted(set(by_prefix[prefix]))
        if not cols:
            continue
        sum_col = f"events_per_second_global_rate_{prefix}"
        summed = pd.Series(0.0, index=out.index, dtype=float)
        valid_any = pd.Series(False, index=out.index, dtype=bool)
        for col in cols:
            numeric = pd.to_numeric(out[col], errors="coerce")
            summed = summed + numeric.fillna(0.0)
            valid_any = valid_any | numeric.notna()
        out[sum_col] = summed.where(valid_any, np.nan)
        rate_col_by_prefix[prefix] = sum_col
        tt_cols_by_prefix[prefix] = cols
    return out, rate_col_by_prefix, tt_cols_by_prefix


def _select_canonical_global_rate(
    df: pd.DataFrame,
    *,
    rate_col_by_prefix: dict[str, str],
    preferred_prefixes: tuple[str, ...],
    fallback_existing_col: str = "events_per_second_global_rate",
) -> tuple[pd.DataFrame, dict[str, int]]:
    out = df.copy()
    canonical = pd.Series(np.nan, index=out.index, dtype=float)
    source_counts: dict[str, int] = {}

    all_prefixes: list[str] = []
    seen: set[str] = set()
    for prefix in preferred_prefixes:
        if prefix in seen:
            continue
        all_prefixes.append(prefix)
        seen.add(prefix)
    for prefix in sorted(rate_col_by_prefix.keys()):
        if prefix in seen:
            continue
        all_prefixes.append(prefix)
        seen.add(prefix)

    for prefix in all_prefixes:
        candidate = rate_col_by_prefix.get(prefix)
        if candidate is None or candidate not in out.columns:
            continue
        vals = pd.to_numeric(out[candidate], errors="coerce")
        fill_mask = canonical.isna() & vals.notna()
        n_fill = int(fill_mask.sum())
        if n_fill > 0:
            canonical = canonical.where(~fill_mask, vals)
            source_counts[prefix] = source_counts.get(prefix, 0) + n_fill

    if fallback_existing_col in out.columns:
        vals = pd.to_numeric(out[fallback_existing_col], errors="coerce")
        fill_mask = canonical.isna() & vals.notna()
        n_fill = int(fill_mask.sum())
        if n_fill > 0:
            canonical = canonical.where(~fill_mask, vals)
            source_counts["fallback_existing_global_rate"] = (
                source_counts.get("fallback_existing_global_rate", 0) + n_fill
            )

    out["events_per_second_global_rate"] = canonical
    return out, source_counts


def _ensure_standard_task_prefix_rate_columns(
    df: pd.DataFrame,
    *,
    rate_col_by_prefix: dict[str, str],
) -> tuple[pd.DataFrame, list[str]]:
    out = df.copy()
    added_cols: list[str] = []
    for prefix in STANDARD_TASK_PREFIXES:
        col = f"events_per_second_global_rate_{prefix}"
        if col in out.columns:
            rate_col_by_prefix.setdefault(prefix, col)
            continue
        out[col] = np.nan
        rate_col_by_prefix[prefix] = col
        added_cols.append(col)
    return out, added_cols


def _compute_eff(n_four: pd.Series, n_three_missing: pd.Series) -> pd.Series:
    denom = n_four + n_three_missing
    return n_four / denom.replace({0: np.nan})


def _compute_empirical_efficiencies(
    df: pd.DataFrame,
    *,
    preferred_prefixes: tuple[str, ...],
) -> tuple[pd.DataFrame, str | None, list[str]]:
    out = df.copy()
    all_prefixes: list[str] = []
    seen: set[str] = set()
    for p in preferred_prefixes:
        if p not in seen:
            all_prefixes.append(p)
            seen.add(p)
    for p in sorted(set(str(m.group("prefix")).strip() for c in out.columns for m in [TT_RATE_COLUMN_RE.match(str(c))] if m)):
        if p not in seen:
            all_prefixes.append(p)
            seen.add(p)

    required_labels = ("1234", "234", "134", "124", "123")
    per_plane_missing = {
        1: "234",
        2: "134",
        3: "124",
        4: "123",
    }

    eff_series = {
        1: pd.Series(np.nan, index=out.index, dtype=float),
        2: pd.Series(np.nan, index=out.index, dtype=float),
        3: pd.Series(np.nan, index=out.index, dtype=float),
        4: pd.Series(np.nan, index=out.index, dtype=float),
    }
    source_prefix = pd.Series("", index=out.index, dtype=object)
    used_prefixes: list[str] = []

    for prefix in all_prefixes:
        four_col = f"{prefix}_1234_rate_hz"
        needed = [f"{prefix}_{lab}_rate_hz" for lab in required_labels]
        if not all(col in out.columns for col in needed):
            continue

        n_four = pd.to_numeric(out[four_col], errors="coerce")
        any_plane_used = False
        for plane in (1, 2, 3, 4):
            miss_label = per_plane_missing[plane]
            miss_col = f"{prefix}_{miss_label}_rate_hz"
            n_miss = pd.to_numeric(out[miss_col], errors="coerce")
            eff_candidate = _compute_eff(n_four, n_miss)
            fill_mask = eff_series[plane].isna() & eff_candidate.notna()
            if bool(fill_mask.any()):
                eff_series[plane] = eff_series[plane].where(~fill_mask, eff_candidate)
                source_prefix = source_prefix.where(~fill_mask, prefix)
                any_plane_used = True
        if any_plane_used:
            used_prefixes.append(prefix)

    for plane in (1, 2, 3, 4):
        out[f"eff_empirical_{plane}"] = eff_series[plane]

    valid_source = source_prefix.astype(str).str.len() > 0
    out["eff_empirical_source_prefix"] = source_prefix.where(valid_source, np.nan)
    selected_prefix = used_prefixes[0] if used_prefixes else None
    return out, selected_prefix, used_prefixes


def _add_derived_physics_helper_columns(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, int]:
    out = _ensure_efficiency_columns(df)
    if not all(col in out.columns for col in ("eff_p1", "eff_p2", "eff_p3", "eff_p4")):
        return out, 0

    eff_cols = ["eff_p1", "eff_p2", "eff_p3", "eff_p4"]
    eff_df = out[eff_cols].apply(pd.to_numeric, errors="coerce")
    valid_eff = eff_df.notna().all(axis=1)
    eff_prod = eff_df.prod(axis=1, min_count=4).where(valid_eff, np.nan)
    out["efficiency_product_4planes"] = eff_prod

    out["efficiency_product_123"] = (
        pd.to_numeric(out["eff_p1"], errors="coerce")
        * pd.to_numeric(out["eff_p2"], errors="coerce")
        * pd.to_numeric(out["eff_p3"], errors="coerce")
    )
    out["efficiency_product_234"] = (
        pd.to_numeric(out["eff_p2"], errors="coerce")
        * pd.to_numeric(out["eff_p3"], errors="coerce")
        * pd.to_numeric(out["eff_p4"], errors="coerce")
    )
    out["efficiency_product_12"] = (
        pd.to_numeric(out["eff_p1"], errors="coerce")
        * pd.to_numeric(out["eff_p2"], errors="coerce")
    )
    out["efficiency_product_34"] = (
        pd.to_numeric(out["eff_p3"], errors="coerce")
        * pd.to_numeric(out["eff_p4"], errors="coerce")
    )

    helper_count = 5
    rate = pd.to_numeric(out.get("events_per_second_global_rate"), errors="coerce")
    product_to_proxy = {
        "efficiency_product_4planes": "flux_proxy_rate_div_effprod",
        "efficiency_product_123": "flux_proxy_rate_div_effprod_123",
        "efficiency_product_234": "flux_proxy_rate_div_effprod_234",
        "efficiency_product_12": "flux_proxy_rate_div_effprod_12",
        "efficiency_product_34": "flux_proxy_rate_div_effprod_34",
    }
    for prod_col, proxy_col in product_to_proxy.items():
        prod = pd.to_numeric(out.get(prod_col), errors="coerce")
        proxy = pd.Series(np.nan, index=out.index, dtype=float)
        valid = prod.notna() & (prod > 0.0) & rate.notna()
        proxy.loc[valid] = rate.loc[valid] / prod.loc[valid]
        out[proxy_col] = proxy
        helper_count += 1
    return out, helper_count


def _normalize_tt_combo_label_list(
    raw: object,
    *,
    default: Sequence[str],
) -> list[str]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raw = list(default)
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        label = _normalize_tt_label(item)
        if label not in CANONICAL_TT_LABELS:
            continue
        if label in seen:
            continue
        seen.add(label)
        out.append(label)
    if not out:
        out = [str(label) for label in default if str(label) in CANONICAL_TT_LABELS]
    return out


def _resolve_post_tt_plane_aggregate_config(
    *,
    feature_space_cfg: Mapping[str, object] | None,
) -> dict[str, object]:
    raw = (
        feature_space_cfg.get("post_tt_plane_aggregates", {})
        if isinstance(feature_space_cfg, Mapping)
        else {}
    )
    if not isinstance(raw, Mapping):
        raw = {}
    source_prefix = str(raw.get("source_prefix", "post_tt")).strip() or "post_tt"
    two_plane_total_column = (
        str(raw.get("two_plane_total_column", "post_tt_two_plane_total_rate_hz")).strip()
        or "post_tt_two_plane_total_rate_hz"
    )
    three_plane_total_column = (
        str(raw.get("three_plane_total_column", "post_tt_three_plane_total_rate_hz")).strip()
        or "post_tt_three_plane_total_rate_hz"
    )
    four_plane_column = (
        str(raw.get("four_plane_column", "post_tt_four_plane_rate_hz")).strip()
        or "post_tt_four_plane_rate_hz"
    )
    return {
        "enabled": bool(raw.get("enabled", True)),
        "source_prefix": source_prefix,
        "two_plane_total_column": two_plane_total_column,
        "three_plane_total_column": three_plane_total_column,
        "four_plane_column": four_plane_column,
        "two_plane_labels": _normalize_tt_combo_label_list(
            raw.get("two_plane_labels"),
            default=DEFAULT_POST_TT_AGGREGATE_TWO_PLANE_LABELS,
        ),
        "three_plane_labels": _normalize_tt_combo_label_list(
            raw.get("three_plane_labels"),
            default=DEFAULT_POST_TT_AGGREGATE_THREE_PLANE_LABELS,
        ),
        "four_plane_label": _normalize_tt_label(
            raw.get("four_plane_label", DEFAULT_POST_TT_AGGREGATE_FOUR_PLANE_LABEL)
        )
        or DEFAULT_POST_TT_AGGREGATE_FOUR_PLANE_LABEL,
    }


def _add_post_tt_plane_aggregate_columns(
    df: pd.DataFrame,
    *,
    aggregate_cfg: Mapping[str, object],
) -> tuple[pd.DataFrame, dict[str, object]]:
    out = df.copy()
    source_prefix = str(aggregate_cfg.get("source_prefix", "post_tt")).strip() or "post_tt"
    two_labels = [str(v) for v in aggregate_cfg.get("two_plane_labels", []) if str(v).strip()]
    three_labels = [str(v) for v in aggregate_cfg.get("three_plane_labels", []) if str(v).strip()]
    four_label = str(aggregate_cfg.get("four_plane_label", DEFAULT_POST_TT_AGGREGATE_FOUR_PLANE_LABEL)).strip()

    mapping: list[tuple[str, list[str]]] = [
        (str(aggregate_cfg.get("two_plane_total_column", "post_tt_two_plane_total_rate_hz")).strip(), two_labels),
        (str(aggregate_cfg.get("three_plane_total_column", "post_tt_three_plane_total_rate_hz")).strip(), three_labels),
        (str(aggregate_cfg.get("four_plane_column", "post_tt_four_plane_rate_hz")).strip(), [four_label]),
    ]

    summary: dict[str, object] = {
        "enabled": True,
        "source_prefix": source_prefix,
        "columns": {},
    }
    for target_col, labels in mapping:
        clean_target = str(target_col).strip()
        clean_labels = [str(lbl).strip() for lbl in labels if str(lbl).strip()]
        if not clean_target:
            continue
        source_cols = [
            f"{source_prefix}_{label}_rate_hz"
            for label in clean_labels
            if f"{source_prefix}_{label}_rate_hz" in out.columns
        ]
        missing_labels = [
            label
            for label in clean_labels
            if f"{source_prefix}_{label}_rate_hz" not in out.columns
        ]
        if source_cols:
            total = pd.Series(0.0, index=out.index, dtype=float)
            valid_any = pd.Series(False, index=out.index, dtype=bool)
            for src_col in source_cols:
                vals = pd.to_numeric(out[src_col], errors="coerce")
                total = total + vals.fillna(0.0)
                valid_any = valid_any | vals.notna()
            out[clean_target] = total.where(valid_any, np.nan)
        else:
            out[clean_target] = np.nan
        summary["columns"][clean_target] = {
            "labels": clean_labels,
            "source_columns": source_cols,
            "missing_labels": missing_labels,
        }

    return out, summary


def _normalize_requested_columns(raw: object) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        text = raw.strip()
        return [text] if text else []
    if isinstance(raw, (list, tuple)):
        out: list[str] = []
        for item in raw:
            if not isinstance(item, str):
                continue
            text = item.strip()
            if text:
                out.append(text)
        return out
    return []


def _resolve_feature_space_plot_suppression_patterns(
    config: Mapping[str, object] | None,
    *,
    step_cfg: Mapping[str, object] | None = None,
) -> list[str]:
    raw = None
    if isinstance(step_cfg, Mapping):
        raw = step_cfg.get(
            "feature_space_lower_triangle_suppressed_patterns",
            step_cfg.get("feature_matrix_suppressed_patterns"),
        )
        # support simpler "prefixes" config keys that user may set
        if raw is None:
            prefixes = step_cfg.get(
                "feature_space_lower_triangle_suppressed_prefixes",
                step_cfg.get("feature_matrix_suppressed_prefixes"),
            )
            if prefixes is not None:
                # convert prefixes to glob patterns
                if isinstance(prefixes, (list, tuple)):
                    raw = [str(p).strip() + "*" if isinstance(p, (str,)) and not any(ch in str(p) for ch in ("*", "?", "[")) else str(p) for p in prefixes]
                else:
                    p = str(prefixes).strip()
                    raw = [p + "*" if p and not any(ch in p for ch in ("*", "?", "[")) else p]
    if raw is None and isinstance(config, Mapping):
        raw = config.get(
            "feature_space_lower_triangle_suppressed_patterns",
            config.get("feature_matrix_suppressed_patterns"),
        )
        if raw is None:
            prefixes = config.get(
                "feature_space_lower_triangle_suppressed_prefixes",
                config.get("feature_matrix_suppressed_prefixes"),
            )
            if prefixes is not None:
                if isinstance(prefixes, (list, tuple)):
                    raw = [str(p).strip() + "*" if isinstance(p, (str,)) and not any(ch in str(p) for ch in ("*", "?", "[")) else str(p) for p in prefixes]
                else:
                    p = str(prefixes).strip()
                    raw = [p + "*" if p and not any(ch in p for ch in ("*", "?", "[")) else p]
    patterns = _normalize_requested_columns(raw)
    if not patterns:
        patterns = list(DEFAULT_FEATURE_SPACE_LOWER_TRIANGLE_SUPPRESSED_PATTERNS)
    out: list[str] = []
    seen: set[str] = set()
    for pattern in patterns:
        text = str(pattern).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _normalize_explicit_column_list(raw: object) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        text = raw.strip()
        return [text] if text else []
    if isinstance(raw, Mapping):
        out: list[str] = []
        for value in raw.values():
            out.extend(_normalize_explicit_column_list(value))
        return out
    if isinstance(raw, (list, tuple)):
        out: list[str] = []
        for item in raw:
            text = str(item).strip()
            if text:
                out.append(text)
        return out
    text = str(raw).strip()
    return [text] if text else []


def _resolve_required_passthrough_columns(
    cfg_12: Mapping[str, object] | None,
) -> list[str]:
    if not isinstance(cfg_12, Mapping):
        return []
    raw = cfg_12.get("required_passthrough_columns")
    if raw is None:
        raw = cfg_12.get("passthrough_columns", cfg_12.get("required_output_columns"))
    cols = _normalize_explicit_column_list(raw)
    out: list[str] = []
    seen: set[str] = set()
    for col in cols:
        name = str(col).strip()
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


def _merge_materialized_with_required_columns(
    *,
    materialized_columns: Sequence[str],
    required_columns: Sequence[str],
    available_columns: Sequence[str],
) -> tuple[list[str], list[str]]:
    available = {str(col).strip() for col in available_columns if str(col).strip()}
    merged: list[str] = []
    seen: set[str] = set()
    for raw_col in list(materialized_columns) + list(required_columns):
        col = str(raw_col).strip()
        if not col or col in seen or col not in available:
            continue
        seen.add(col)
        merged.append(col)
    missing_required = [
        str(col).strip()
        for col in required_columns
        if str(col).strip() and str(col).strip() not in available
    ]
    return merged, missing_required


def _coerce_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return bool(default)
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return bool(default)


def _resolve_column_transformations(
    *,
    feature_space_cfg: Mapping[str, object] | None,
) -> dict[str, object]:
    raw = (
        feature_space_cfg.get("column_transformations", {})
        if isinstance(feature_space_cfg, Mapping)
        else {}
    )
    if not isinstance(raw, Mapping):
        raw = {}
    if not raw and isinstance(feature_space_cfg, Mapping):
        if any(key in feature_space_cfg for key in ("kept", "new", "keep_dimensions", "new_dimensions", "columns")):
            columns_cfg = feature_space_cfg.get("columns")
            if isinstance(columns_cfg, Mapping):
                raw = {
                    "keep_dimensions": columns_cfg.get(
                        "kept",
                        columns_cfg.get("keep", columns_cfg.get("keep_dimensions")),
                    ),
                    "new_dimensions": columns_cfg.get(
                        "new",
                        columns_cfg.get("new_dimensions", columns_cfg.get("new_columns")),
                    ),
                }
            else:
                raw = {
                    "keep_dimensions": feature_space_cfg.get(
                        "kept",
                        feature_space_cfg.get("keep_dimensions", feature_space_cfg.get("keep")),
                    ),
                    "new_dimensions": feature_space_cfg.get(
                        "new",
                        feature_space_cfg.get("new_dimensions", feature_space_cfg.get("new_columns")),
                    ),
                }
    enabled = _coerce_bool(raw.get("enabled", True), default=True)
    keep_dimensions = _normalize_explicit_column_list(
        raw.get("keep_dimensions", raw.get("keep_columns", raw.get("kept", raw.get("keep"))))
    )
    new_dimensions_raw = raw.get("new_dimensions", raw.get("new_columns", raw.get("new", {})))
    new_dimensions: dict[str, str] = {}
    if isinstance(new_dimensions_raw, Mapping):
        for key, expr in new_dimensions_raw.items():
            if isinstance(expr, Mapping):
                for sub_key, sub_expr in expr.items():
                    name = str(sub_key).strip()
                    if not name:
                        continue
                    text = str(sub_expr).strip()
                    if not text:
                        continue
                    new_dimensions[name] = text
                continue
            name = str(key).strip()
            if not name:
                continue
            text = str(expr).strip()
            if not text:
                continue
            new_dimensions[name] = text
    enabled = bool(enabled) and (bool(keep_dimensions) or bool(new_dimensions))
    return {
        "enabled": enabled,
        "keep_dimensions": keep_dimensions,
        "new_dimensions": new_dimensions,
    }


_ALLOWED_BINOPS: dict[type, object] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}
_ALLOWED_UNARYOPS: dict[type, object] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _evaluate_column_expression(
    *,
    df: pd.DataFrame,
    expression: str,
) -> pd.Series:
    def _eval_node(node: ast.AST) -> pd.Series | float:
        if isinstance(node, ast.Expression):
            return _eval_node(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)) and np.isfinite(node.value):
                return float(node.value)
            raise ValueError("Only numeric constants are allowed.")
        if isinstance(node, ast.Name):
            name = str(node.id)
            if name not in df.columns:
                raise KeyError(f"Column '{name}' not found for expression.")
            return pd.to_numeric(df[name], errors="coerce")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id != "col":
                raise ValueError("Only col('column_name') calls are allowed.")
            if len(node.args) != 1 or not isinstance(node.args[0], ast.Constant):
                raise ValueError("col() requires a single string literal.")
            col_name = node.args[0].value
            if not isinstance(col_name, str):
                raise ValueError("col() requires a string literal.")
            if col_name not in df.columns:
                raise KeyError(f"Column '{col_name}' not found for expression.")
            return pd.to_numeric(df[col_name], errors="coerce")
        if isinstance(node, ast.UnaryOp):
            op = _ALLOWED_UNARYOPS.get(type(node.op))
            if op is None:
                raise ValueError("Unsupported unary operator in expression.")
            return op(_eval_node(node.operand))
        if isinstance(node, ast.BinOp):
            op = _ALLOWED_BINOPS.get(type(node.op))
            if op is None:
                raise ValueError("Unsupported binary operator in expression.")
            return op(_eval_node(node.left), _eval_node(node.right))
        raise ValueError(f"Unsupported expression node: {type(node).__name__}")

    parsed = ast.parse(expression, mode="eval")
    result = _eval_node(parsed)
    if isinstance(result, pd.Series):
        return result
    return pd.Series(result, index=df.index, dtype=float)


def _apply_column_transformations(
    df: pd.DataFrame,
    *,
    transform_cfg: Mapping[str, object],
) -> tuple[pd.DataFrame, dict[str, object], list[str]]:
    out = df.copy()
    info: dict[str, object] = {
        "enabled": True,
        "keep_dimensions": list(transform_cfg.get("keep_dimensions", [])),
        "new_dimensions": dict(transform_cfg.get("new_dimensions", {})),
        "applied": False,
    }
    missing_keep: list[str] = []

    new_dims = transform_cfg.get("new_dimensions", {})
    if isinstance(new_dims, Mapping):
        for name, expr in new_dims.items():
            try:
                out[name] = _evaluate_column_expression(df=out, expression=str(expr))
            except Exception as exc:
                raise ValueError(f"Failed to evaluate expression for '{name}': {exc}") from exc
            log.info("Derived column from expression: %s <= %s", name, expr)

    keep_dimensions = [
        str(col).strip()
        for col in transform_cfg.get("keep_dimensions", [])
        if str(col).strip()
    ]
    for col in keep_dimensions:
        if col not in out.columns:
            missing_keep.append(col)

    keep_order: list[str] = []
    seen: set[str] = set()
    for col in keep_dimensions + list(new_dims.keys() if isinstance(new_dims, Mapping) else []):
        name = str(col).strip()
        if not name or name in seen:
            continue
        seen.add(name)
        keep_order.append(name)

    info["applied"] = True
    info["final_keep_dimensions"] = list(keep_order)
    info["missing_keep_dimensions"] = list(missing_keep)

    if missing_keep:
        return out, info, missing_keep
    return out, info, []


def _normalize_derived_columns_catalog(
    raw: object,
) -> list[dict[str, str]]:
    source = raw
    if source is None:
        source = DEFAULT_DERIVED_COLUMNS_CATALOG

    entries: list[dict[str, str]] = []
    if isinstance(source, Mapping):
        for key, value in source.items():
            pattern = str(key).strip()
            if not pattern:
                continue
            if isinstance(value, Mapping):
                src = str(value.get("source", "")).strip()
                when = str(value.get("generated_when", "")).strip()
            else:
                src = str(value).strip()
                when = ""
            entries.append(
                {
                    "column_pattern": pattern,
                    "source": src,
                    "generated_when": when,
                }
            )
    elif isinstance(source, Sequence) and not isinstance(source, (str, bytes)):
        for item in source:
            if not isinstance(item, Mapping):
                continue
            pattern = str(item.get("column_pattern", item.get("column", ""))).strip()
            if not pattern:
                continue
            entries.append(
                {
                    "column_pattern": pattern,
                    "source": str(item.get("source", "")).strip(),
                    "generated_when": str(item.get("generated_when", "")).strip(),
                }
            )
    else:
        return _normalize_derived_columns_catalog(DEFAULT_DERIVED_COLUMNS_CATALOG)

    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for entry in entries:
        pattern = str(entry.get("column_pattern", "")).strip()
        if not pattern or pattern in seen:
            continue
        seen.add(pattern)
        out.append(
            {
                "column_pattern": pattern,
                "source": str(entry.get("source", "")).strip(),
                "generated_when": str(entry.get("generated_when", "")).strip(),
            }
        )
    return out


def _catalog_presence_against_columns(
    *,
    catalog_entries: Sequence[Mapping[str, str]],
    available_columns: Sequence[object],
    transform_options: Mapping[str, object] | None = None,
) -> tuple[list[dict[str, object]], list[str]]:
    transform_cfg = transform_options if isinstance(transform_options, Mapping) else {}

    def _is_expected_active(entry: Mapping[str, str]) -> bool:
        when = str(entry.get("generated_when", "")).strip().lower()
        if not when or when.startswith("always"):
            return True
        if "derive_canonical_global_rate" in when:
            return bool(transform_cfg.get("derive_canonical_global_rate", True))
        if "derive_empirical_efficiencies" in when:
            return bool(transform_cfg.get("derive_empirical_efficiencies", True))
        if "derive_physics_helpers" in when:
            return bool(transform_cfg.get("derive_physics_helpers", True))
        if "derive_post_tt_plane_aggregates" in when:
            return bool(transform_cfg.get("derive_post_tt_plane_aggregates", False))
        if "column_transformations" in when:
            return bool(transform_cfg.get("column_transformations", False))
        return True

    available = [str(col) for col in available_columns if str(col).strip()]
    available_set = set(available)
    presence: list[dict[str, object]] = []
    unmatched_patterns: list[str] = []
    for entry in catalog_entries:
        pattern = str(entry.get("column_pattern", "")).strip()
        if not pattern:
            continue
        expected_active = _is_expected_active(entry)
        glob_pattern = pattern.replace("{prefix}", "*")
        if any(ch in glob_pattern for ch in ("*", "?", "[")):
            matches = [col for col in available if fnmatch.fnmatchcase(col, glob_pattern)]
        else:
            matches = [glob_pattern] if glob_pattern in available_set else []
        if expected_active and (not matches):
            unmatched_patterns.append(pattern)
        preview = list(matches[:20])
        presence.append(
            {
                "column_pattern": pattern,
                "source": str(entry.get("source", "")).strip(),
                "generated_when": str(entry.get("generated_when", "")).strip(),
                "expected_active": bool(expected_active),
                "matched_count": int(len(matches)),
                "matched_columns_preview": preview,
                "matched_columns_truncated": bool(len(matches) > len(preview)),
            }
        )
    return presence, unmatched_patterns


def _resolve_configured_keep_columns(
    df: pd.DataFrame,
    *,
    requested_patterns: list[str],
) -> tuple[list[str], list[str]]:
    available = list(df.columns)
    available_set = set(available)
    resolved: list[str] = []
    seen: set[str] = set()
    unmatched: list[str] = []

    for pattern in requested_patterns:
        if any(ch in pattern for ch in ("*", "?", "[")):
            matches = [c for c in available if fnmatch.fnmatchcase(c, pattern)]
        else:
            matches = [pattern] if pattern in available_set else []
        if not matches:
            unmatched.append(pattern)
            continue
        for col in matches:
            if col in seen:
                continue
            resolved.append(col)
            seen.add(col)
    return resolved, unmatched


def _normalize_plot_pairs(raw: object) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    if not isinstance(raw, (list, tuple)):
        return out
    for item in raw:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            continue
        x, y = item
        if not isinstance(x, str) or not isinstance(y, str):
            continue
        xs = x.strip()
        ys = y.strip()
        if not xs or not ys:
            continue
        out.append((xs, ys))
    return out


def _load_selected_feature_columns(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(payload, dict):
        return []
    cols = payload.get("selected_feature_columns", [])
    if not isinstance(cols, list):
        return []
    out: list[str] = []
    for col in cols:
        if not isinstance(col, str):
            continue
        text = col.strip()
        if text:
            out.append(text)
    return out


def _load_parameter_space_columns(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(payload, dict):
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
            seen.add(text)
            out.append(text)
        if out:
            break
    return out


def _select_best_tt_prefix(
    available_prefixes: set[str],
    *,
    priority: tuple[str, ...],
) -> str | None:
    """Return the highest-priority tt prefix that is present in the data."""
    for p in priority:
        if p in available_prefixes:
            return p
    if available_prefixes:
        return sorted(available_prefixes)[0]
    return None


def _drop_non_best_tt_columns(
    df: pd.DataFrame,
    *,
    best_prefix: str | None,
    tt_cols_by_prefix: dict[str, list[str]],
    rate_col_by_prefix: dict[str, str],
) -> tuple[pd.DataFrame, list[str]]:
    """Drop individual tt-rate columns and per-prefix global-rate summaries for all
    prefixes except *best_prefix*.

    The two dictionaries are iterated independently so that per-prefix global-rate
    columns (events_per_second_global_rate_{prefix}) are always cleaned up even when
    no individual breakdown columns exist (tt_cols_by_prefix is empty).
    """
    if best_prefix is None:
        return df, []
    drop_set: set[str] = set()
    # Individual tt-rate breakdown columns (prefix_tt_{label}_rate_hz)
    for prefix, cols in tt_cols_by_prefix.items():
        if prefix == best_prefix:
            continue
        drop_set.update(c for c in cols if c in df.columns)
    # Per-prefix global-rate summary columns (events_per_second_global_rate_{prefix})
    # are all redundant: the canonical events_per_second_global_rate already holds
    # the value from the best prefix, so drop every per-prefix variant.
    for prefix, rate_col in rate_col_by_prefix.items():
        if rate_col in df.columns:
            drop_set.add(rate_col)
    drop_cols = list(drop_set)
    if not drop_cols:
        return df, []
    return df.drop(columns=drop_cols), drop_cols


def _is_rate_histogram_feature(col: str) -> bool:
    return HIST_RATE_COLUMN_RE.match(str(col)) is not None


EFF_VEC_COLUMN_RE = re.compile(r"^efficiency_vector_p\d+_(?:x|y|theta)_bin_\d+_eff$")


def _is_efficiency_vector_feature(col: str) -> bool:
    return EFF_VEC_COLUMN_RE.match(str(col)) is not None


def _resolve_feature_matrix_plot_columns(
    feature_cols: list[str],
    *,
    include_rate_histogram: bool,
    include_efficiency_vectors: bool = True,
    suppressed_patterns: Sequence[str] | None = None,
) -> tuple[list[str], list[str], list[str], bool, bool]:
    """Return plotting columns with optional suppression placeholders.

    Returns: (plot_cols, hist_cols, eff_cols, hist_placeholder_added, eff_placeholder_added)
    """
    base = [c for c in feature_cols if isinstance(c, str) and c.strip()]
    hist_cols = [c for c in base if _is_rate_histogram_feature(c)]
    eff_cols = [c for c in base if _is_efficiency_vector_feature(c)]
    # Remove hist/eff cols from scalar list
    non_group_cols = [c for c in base if c not in set(hist_cols) and c not in set(eff_cols)]
    patterns = [str(p).strip() for p in (suppressed_patterns or []) if str(p).strip()]
    suppress_hist_by_pattern = any(
        fnmatch.fnmatchcase(col, pattern)
        for pattern in patterns
        for col in hist_cols
    )
    suppress_eff_by_pattern = any(
        fnmatch.fnmatchcase(col, pattern)
        for pattern in patterns
        for col in eff_cols
    )

    hist_placeholder_added = False
    eff_placeholder_added = False
    plot_cols: list[str] = list(non_group_cols)

    if (include_rate_histogram and not suppress_hist_by_pattern) or not hist_cols:
        plot_cols.extend(hist_cols)
    else:
        plot_cols.append(RATE_HIST_PLACEHOLDER_COL)
        hist_placeholder_added = True

    if (include_efficiency_vectors and not suppress_eff_by_pattern) or not eff_cols:
        plot_cols.extend(eff_cols)
    else:
        plot_cols.append(EFF_PLACEHOLDER_COL)
        eff_placeholder_added = True

    return plot_cols, hist_cols, eff_cols, hist_placeholder_added, eff_placeholder_added


def _default_step13_like_feature_columns(df: pd.DataFrame) -> list[str]:
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
    return [c for c in df.columns if c not in exclude]


def _resolve_parameter_matrix_columns(
    df: pd.DataFrame,
    *,
    cfg_12: dict,
    cfg_14: dict,
    parameter_space_path: Path,
) -> tuple[list[str], list[str], str]:
    raw = cfg_12.get("parameter_matrix_columns", "auto")
    requested: list[str]
    source = "step_1_2.parameter_matrix_columns"
    if isinstance(raw, str) and raw.strip().lower() == "auto":
        requested = _load_parameter_space_columns(parameter_space_path)
        if requested:
            source = f"artifact:{parameter_space_path.name}"
        else:
            requested = _normalize_requested_columns(cfg_14.get("parameter_columns"))
            if requested:
                source = "step_1_4.parameter_columns"
            else:
                requested = [
                    "flux_cm2_min",
                    "eff_sim_1",
                    "eff_sim_2",
                    "eff_sim_3",
                    "eff_sim_4",
                    "cos_n",
                ]
                source = "internal_fallback"
    else:
        requested = _normalize_requested_columns(raw)
        source = "step_1_2.parameter_matrix_columns"

    resolved, unmatched = _resolve_configured_keep_columns(
        df,
        requested_patterns=requested,
    )
    return resolved, unmatched, source


def _resolve_feature_matrix_columns(
    df: pd.DataFrame,
    *,
    cfg_12: dict,
    config: dict,
    feature_space_cfg: dict,
    parameter_cols: list[str],
) -> tuple[list[str], list[str], str]:
    raw = cfg_12.get("feature_matrix_columns", "auto")
    parameter_set = set(parameter_cols)

    if isinstance(raw, str) and raw.strip().lower() == "auto":
        feature_dimensions = extract_feature_dimensions(feature_space_cfg)
        fallback_columns = feature_dimensions if feature_dimensions else []
        selected_cfg_cols, selected_cfg_info = resolve_selected_feature_space_columns(
            available_columns=list(df.columns),
            feature_space_cfg=feature_space_cfg,
            fallback_columns=fallback_columns,
        )
        if selected_cfg_info.get("used_feature_space_config") and selected_cfg_cols:
            cols = [c for c in selected_cfg_cols if c in df.columns and c not in parameter_set]
            if cols:
                unmatched = list(selected_cfg_info.get("unmatched_include_patterns", []))
                return cols, unmatched, str(selected_cfg_info.get("source"))

        for candidate_path in (DEFAULT_STEP14_SELECTED_FEATURES, DEFAULT_STEP13_SELECTED_FEATURES):
            selected = _load_selected_feature_columns(candidate_path)
            if selected:
                cols = [c for c in selected if c in df.columns and c not in parameter_set]
                unmatched = [c for c in selected if c not in df.columns]
                if cols:
                    return cols, unmatched, f"artifact:{candidate_path.name}"

        common_cfg = config.get("common_feature_space", {}) if isinstance(config, dict) else {}
        common_raw = common_cfg.get("feature_columns")
        if not (
            isinstance(common_raw, str)
            and common_raw.strip().lower() in {"", "auto", "step12_selected", "selected", "selected_json"}
        ):
            patterns = _normalize_requested_columns(common_raw)
            resolved, unmatched = _resolve_configured_keep_columns(df, requested_patterns=patterns)
            cols = [c for c in resolved if c not in parameter_set]
            if cols:
                return cols, unmatched, "common_feature_space.feature_columns"

        cols = [c for c in _default_step13_like_feature_columns(df) if c not in parameter_set]
        return cols, [], "step13_style_fallback"

    requested = _normalize_requested_columns(raw)
    resolved, unmatched = _resolve_configured_keep_columns(df, requested_patterns=requested)
    cols = [c for c in resolved if c not in parameter_set]
    return cols, unmatched, "step_1_2.feature_matrix_columns"


def _plot_parameter_scatter_matrix(
    df: pd.DataFrame,
    *,
    parameter_cols: list[str],
    sample_max_rows: int,
    random_seed: int,
) -> None:
    cols = [c for c in parameter_cols if c in df.columns]
    if len(cols) < 2:
        return

    plot_df = df
    if sample_max_rows > 0 and len(plot_df) > sample_max_rows:
        plot_df = plot_df.sample(n=sample_max_rows, random_state=random_seed)

    n = len(cols)
    fig, axes = plt.subplots(n, n, figsize=(2.8 * n, 2.8 * n), squeeze=False)
    for i, cy in enumerate(cols):
        for j, cx in enumerate(cols):
            ax = axes[i, j]
            if i == j:
                vals = pd.to_numeric(plot_df[cx], errors="coerce").dropna()
                if vals.empty:
                    ax.set_visible(False)
                    continue
                ax.hist(vals.to_numpy(dtype=float), bins=35, color="#4C78A8", alpha=0.75)
                ax.set_xlabel(cx, fontsize=7)
                ax.set_ylabel("Rows", fontsize=7)
                ax.grid(True, alpha=0.2)
            elif i > j:
                x = pd.to_numeric(plot_df[cx], errors="coerce")
                y = pd.to_numeric(plot_df[cy], errors="coerce")
                m = x.notna() & y.notna()
                if bool(m.any()):
                    ax.scatter(
                        x[m].to_numpy(dtype=float),
                        y[m].to_numpy(dtype=float),
                        s=7,
                        alpha=0.28,
                        color="#4C78A8",
                        edgecolors="none",
                    )
                ax.set_xlabel(cx, fontsize=7)
                ax.set_ylabel(cy, fontsize=7)
                ax.grid(True, alpha=0.2)
            else:
                ax.axis("off")
            ax.tick_params(labelsize=6)

    fig.suptitle("STEP 1.2 parameter scatter matrix (lower-triangle)", y=0.995, fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.985])
    _save_figure(fig, PLOTS_DIR / "parameter_scatter_matrix.png", dpi=150)
    plt.close(fig)


def _plot_feature_scatter_matrix(
    df: pd.DataFrame,
    *,
    feature_cols: list[str],
    sample_max_rows: int,
    random_seed: int,
    rate_hist_suppressed_count: int = 0,
    eff_suppressed_count: int = 0,
    max_side: int | None = None,
) -> None:
    cols = [
        c
        for c in feature_cols
        if c in (RATE_HIST_PLACEHOLDER_COL, EFF_PLACEHOLDER_COL) or c in df.columns
    ]
    max_side_int = int(max_side) if max_side is not None else 0
    if max_side_int > 0 and len(cols) > max_side_int:
        placeholders = [c for c in cols if c in (RATE_HIST_PLACEHOLDER_COL, EFF_PLACEHOLDER_COL)]
        others = [c for c in cols if c not in placeholders]
        keep_slots = max(max_side_int - len(placeholders), 0)
        cols = placeholders + others[:keep_slots]
        cols = cols[:max_side_int]
        log.info(
            "Feature scatter matrix capped at %d column(s) (from %d).",
            max_side_int,
            len(feature_cols),
        )
    if len(cols) < 2:
        return

    plot_df = df
    if sample_max_rows > 0 and len(plot_df) > sample_max_rows:
        plot_df = plot_df.sample(n=sample_max_rows, random_state=random_seed)

    n = len(cols)
    if n > 40 and len(plot_df) > 700:
        plot_df = plot_df.sample(n=700, random_state=random_seed)
    elif n > 24 and len(plot_df) > 1200:
        plot_df = plot_df.sample(n=1200, random_state=random_seed)

    if n <= 12:
        cell = 2.4
    elif n <= 24:
        cell = 1.5
    elif n <= 40:
        cell = 1.0
    else:
        cell = 0.78

    fig, axes = plt.subplots(n, n, figsize=(cell * n, cell * n), squeeze=False)
    diag_bins = 28 if n <= 24 else 16
    point_size = 7 if n <= 24 else 3

    for i, cy in enumerate(cols):
        for j, cx in enumerate(cols):
            ax = axes[i, j]
            x_is_placeholder = (cx == RATE_HIST_PLACEHOLDER_COL)
            y_is_placeholder = (cy == RATE_HIST_PLACEHOLDER_COL)
            x_is_eff_placeholder = (cx == EFF_PLACEHOLDER_COL)
            y_is_eff_placeholder = (cy == EFF_PLACEHOLDER_COL)
            if i == j:
                if x_is_placeholder or x_is_eff_placeholder:
                    ax.set_facecolor("#F2F2F2")
                    if x_is_placeholder:
                        msg = "Rate-histogram block\nsuppressed for display"
                        if rate_hist_suppressed_count > 0:
                            msg = f"Rate-histogram block suppressed\n({rate_hist_suppressed_count} columns)"
                        label = RATE_HIST_PLACEHOLDER_LABEL
                    else:
                        msg = "Efficiency-vector block\nsuppressed for display"
                        if eff_suppressed_count > 0:
                            msg = f"Efficiency-vector block suppressed\n({eff_suppressed_count} columns)"
                        label = EFF_PLACEHOLDER_LABEL
                    ax.text(
                        0.5,
                        0.5,
                        msg,
                        ha="center",
                        va="center",
                        fontsize=5.8,
                        transform=ax.transAxes,
                    )
                    if i == n - 1:
                        ax.set_xlabel(label, fontsize=5.5)
                    else:
                        ax.set_xticklabels([])
                    if j == 0:
                        ax.set_ylabel("Rows", fontsize=5.5)
                    else:
                        ax.set_yticklabels([])
                    ax.tick_params(labelsize=4.8, length=1.5)
                    ax.grid(True, alpha=0.12)
                    continue

                vals = pd.to_numeric(plot_df[cx], errors="coerce").dropna()
                if vals.empty:
                    ax.set_visible(False)
                    continue
                ax.hist(vals.to_numpy(dtype=float), bins=diag_bins, color="#4C78A8", alpha=0.70)
                if i == n - 1:
                    ax.set_xlabel(cx, fontsize=5.5)
                else:
                    ax.set_xticklabels([])
                if j == 0:
                    ax.set_ylabel("Rows", fontsize=5.5)
                else:
                    ax.set_yticklabels([])
                ax.grid(True, alpha=0.15)
            elif i > j:
                if x_is_placeholder or y_is_placeholder or x_is_eff_placeholder or y_is_eff_placeholder:
                    ax.set_facecolor("#F7F7F7")
                    # choose appropriate labels for axes that are placeholders
                    xlabel = RATE_HIST_PLACEHOLDER_LABEL if x_is_placeholder else (EFF_PLACEHOLDER_LABEL if x_is_eff_placeholder else cx)
                    ylabel = RATE_HIST_PLACEHOLDER_LABEL if y_is_placeholder else (EFF_PLACEHOLDER_LABEL if y_is_eff_placeholder else cy)
                    if i == n - 1:
                        ax.set_xlabel(xlabel if isinstance(xlabel, str) else cx, fontsize=5.5)
                    else:
                        ax.set_xticklabels([])
                    if j == 0:
                        ax.set_ylabel(ylabel if isinstance(ylabel, str) else cy, fontsize=5.5)
                    else:
                        ax.set_yticklabels([])
                    ax.tick_params(labelsize=4.8, length=1.5)
                    ax.grid(True, alpha=0.10)
                    continue

                x = pd.to_numeric(plot_df[cx], errors="coerce")
                y = pd.to_numeric(plot_df[cy], errors="coerce")
                m = x.notna() & y.notna()
                if bool(m.any()):
                    ax.scatter(
                        x[m].to_numpy(dtype=float),
                        y[m].to_numpy(dtype=float),
                        s=point_size,
                        alpha=0.22,
                        color="#4C78A8",
                        edgecolors="none",
                        rasterized=True,
                    )
                if i == n - 1:
                    ax.set_xlabel(cx, fontsize=5.5)
                else:
                    ax.set_xticklabels([])
                if j == 0:
                    ax.set_ylabel(cy, fontsize=5.5)
                else:
                    ax.set_yticklabels([])
                ax.grid(True, alpha=0.15)
            else:
                ax.axis("off")
            ax.tick_params(labelsize=4.8, length=1.5)

    fig.suptitle("STEP 1.2 feature-space scatter matrix (lower-triangle)", y=0.998, fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.992])
    _save_figure(fig, PLOTS_DIR / "feature_scatter_matrix.png", dpi=140)
    plt.close(fig)


def _make_grouped_feature_space_summary_plot(
    df: pd.DataFrame,
    *,
    selected_feature_cols: list[str],
    out_path: Path | None = None,
) -> dict[str, object]:
    dd = load_distance_definition(selected_feature_cols) if selected_feature_cols else {"available": False}
    dd_group_weights = dd.get("group_weights", {}) if isinstance(dd, dict) else {}
    if not isinstance(dd_group_weights, dict):
        dd_group_weights = {}
    dd_feature_groups = dd.get("feature_groups", {}) if isinstance(dd, dict) else {}
    if not isinstance(dd_feature_groups, dict):
        dd_feature_groups = {}

    hist_cfg = dd_feature_groups.get("rate_histogram", {})
    if not isinstance(hist_cfg, dict):
        hist_cfg = {}
    hist_active = (not dd_group_weights) or float(dd_group_weights.get("rate_histogram", 0.0)) > 0.0
    hist_cols = [
        str(col)
        for col in hist_cfg.get("feature_columns", [])
        if str(col) in df.columns
    ]
    if not hist_cols and hist_active:
        hist_cols = sorted(
            [str(c) for c in df.columns if HIST_RATE_COLUMN_RE.match(str(c))],
            key=lambda c: int(HIST_RATE_COLUMN_RE.match(str(c)).group("bin")) if HIST_RATE_COLUMN_RE.match(str(c)) else 0,
        )

    eff_cfg = dd_feature_groups.get("efficiency_vectors", {})
    if not isinstance(eff_cfg, dict):
        eff_cfg = {}
    eff_active = (not dd_group_weights) or float(dd_group_weights.get("efficiency_vectors", 0.0)) > 0.0
    eff_payloads: list[dict[str, object]] = []
    if eff_active:
        eff_payloads = _prepare_efficiency_vector_group_payloads(dict_df=df, data_df=df)
        eff_payloads = _filter_efficiency_vector_payloads(
            eff_payloads,
            feature_groups_cfg=eff_cfg if eff_cfg else None,
            selected_feature_columns=selected_feature_cols,
        )

    axis_payloads: dict[str, list[dict[str, object]]] = {"x": [], "y": [], "theta": []}
    for payload in eff_payloads:
        axis_name = str(payload.get("axis", "")).strip().lower()
        if axis_name in axis_payloads:
            axis_payloads[axis_name].append(payload)

    axes_to_plot = [axis for axis in ("x", "y", "theta") if axis_payloads[axis]]
    n_panels = (1 if hist_cols else 0) + len(axes_to_plot)
    summary: dict[str, object] = {
        "status": "unavailable",
        "distance_definition_available": bool(dd.get("available")) if isinstance(dd, dict) else False,
        "rate_histogram_bins_used": int(len(hist_cols)),
        "efficiency_vector_groups_used": int(len(eff_payloads)),
        "efficiency_vector_axes_used": axes_to_plot,
    }

    plot_path = out_path or (PLOTS_DIR / "feature_grouped_summary.png")
    if n_panels == 0:
        fig, ax = plt.subplots(figsize=(8.8, 4.2))
        ax.axis("off")
        ax.text(
            0.5,
            0.5,
            "No grouped feature-space blocks are available for summary plotting.",
            ha="center",
            va="center",
            fontsize=11,
            transform=ax.transAxes,
        )
        fig.suptitle("STEP 1.2 grouped feature-space summary", fontsize=12, y=0.96)
        _save_figure(fig, plot_path, dpi=150)
        plt.close(fig)
        summary["status"] = "no_grouped_blocks"
        return summary

    fig, axes = plt.subplots(
        n_panels,
        1,
        figsize=(11.2, max(3.0 * n_panels, 4.8)),
        squeeze=False,
    )
    axes_flat = axes[:, 0]
    panel_idx = 0

    if hist_cols:
        ax = axes_flat[panel_idx]
        panel_idx += 1
        hist_bins = np.asarray(
            [int(HIST_RATE_COLUMN_RE.match(col).group("bin")) for col in hist_cols],
            dtype=float,
        )
        hist_frame = df[hist_cols].apply(pd.to_numeric, errors="coerce")
        hist_med = hist_frame.median(axis=0, skipna=True).to_numpy(dtype=float)
        hist_lo = hist_frame.quantile(0.25).to_numpy(dtype=float)
        hist_hi = hist_frame.quantile(0.75).to_numpy(dtype=float)
        ax.fill_between(hist_bins, hist_lo, hist_hi, color="#BDBDBD", alpha=0.28, label="IQR")
        ax.plot(hist_bins, hist_med, color="#1F77B4", linewidth=1.8, label="Median")
        ax.set_xlabel("Rate-histogram bin index", fontsize=8)
        ax.set_ylabel("Rate [Hz]", fontsize=8)
        ax.set_title("Rate histogram summary across transformed rows", fontsize=9)
        ax.grid(True, alpha=0.18)
        ax.legend(fontsize=7, loc="upper right", frameon=False)

    plane_colors = {
        1: "#1F77B4",
        2: "#FF7F0E",
        3: "#2CA02C",
        4: "#D62728",
    }
    for axis_name in axes_to_plot:
        ax = axes_flat[panel_idx]
        panel_idx += 1
        for payload in sorted(axis_payloads[axis_name], key=lambda item: int(item.get("plane", 0))):
            centers = np.asarray(payload.get("centers", []), dtype=float)
            if centers.size == 0:
                continue
            eff_frame = pd.DataFrame(np.asarray(payload.get("dict_eff", []), dtype=float))
            if eff_frame.empty:
                continue
            eff_med = eff_frame.median(axis=0, skipna=True).to_numpy(dtype=float)
            eff_lo = eff_frame.quantile(0.25).to_numpy(dtype=float)
            eff_hi = eff_frame.quantile(0.75).to_numpy(dtype=float)
            plane = int(payload.get("plane", 0))
            color = plane_colors.get(plane, "#4C78A8")
            valid = np.isfinite(centers) & np.isfinite(eff_med)
            if not np.any(valid):
                continue
            ax.fill_between(
                centers[valid],
                eff_lo[valid],
                eff_hi[valid],
                color=color,
                alpha=0.12,
            )
            ax.plot(
                centers[valid],
                eff_med[valid],
                color=color,
                linewidth=1.5,
                label=f"Plane {plane}",
            )
        axis_label = {
            "x": "Projected X [mm]",
            "y": "Projected Y [mm]",
            "theta": "Theta [deg]",
        }.get(axis_name, axis_name)
        ax.set_xlabel(axis_label, fontsize=8)
        ax.set_ylabel("Efficiency", fontsize=8)
        ax.set_ylim(0.0, 1.05)
        ax.set_title(f"Efficiency-vector summary vs {axis_name}", fontsize=9)
        ax.grid(True, alpha=0.18)
        handles, labels = ax.get_legend_handles_labels()
        if handles:
            ax.legend(fontsize=7, loc="best", frameon=False, ncol=min(4, len(handles)))

    fig.suptitle("STEP 1.2 grouped feature-space summary", fontsize=12, y=0.995)
    fig.tight_layout(rect=[0, 0, 1, 0.985])
    _save_figure(fig, plot_path, dpi=150)
    plt.close(fig)
    summary["status"] = "ok"
    summary["n_panels"] = int(n_panels)
    return summary


def _select_grouped_multicase_rows(
    df: pd.DataFrame,
    *,
    n_cases: int,
    random_seed: int,
) -> np.ndarray:
    n_rows = len(df)
    if n_rows == 0 or n_cases <= 0:
        return np.asarray([], dtype=int)
    n_cases = min(int(n_cases), n_rows)
    if "flux_cm2_min" in df.columns:
        flux = pd.to_numeric(df["flux_cm2_min"], errors="coerce").to_numpy(dtype=float)
        valid_idx = np.flatnonzero(np.isfinite(flux))
        if valid_idx.size > 0:
            order = valid_idx[np.argsort(flux[valid_idx], kind="mergesort")]
            pick_pos = np.linspace(0, max(order.size - 1, 0), num=n_cases)
            pick = order[np.clip(np.round(pick_pos).astype(int), 0, max(order.size - 1, 0))]
            pick = np.unique(pick)
            if pick.size < n_cases:
                rng = np.random.default_rng(int(random_seed))
                remaining = np.setdiff1d(np.arange(n_rows, dtype=int), pick, assume_unique=False)
                if remaining.size > 0:
                    extra = rng.choice(remaining, size=min(n_cases - pick.size, remaining.size), replace=False)
                    pick = np.sort(np.concatenate([pick, np.asarray(extra, dtype=int)]))
            return np.asarray(pick[:n_cases], dtype=int)
    rng = np.random.default_rng(int(random_seed))
    return np.sort(rng.choice(np.arange(n_rows, dtype=int), size=n_cases, replace=False))


def _apply_grouped_fiducial_overlay(
    ax: plt.Axes,
    *,
    axis_name: str,
    fiducial: dict[str, object] | None,
) -> None:
    cfg = fiducial if isinstance(fiducial, dict) else {}
    if axis_name == "theta":
        limit = cfg.get("theta_max_deg")
    elif axis_name == "x":
        limit = cfg.get("x_abs_max_mm")
    elif axis_name == "y":
        limit = cfg.get("y_abs_max_mm")
    else:
        limit = None
    try:
        limit_val = float(limit) if limit is not None else np.nan
    except (TypeError, ValueError):
        limit_val = np.nan
    if not np.isfinite(limit_val) or limit_val <= 0.0:
        return
    ax.axvspan(-limit_val, limit_val, color="#59A14F", alpha=0.08, zorder=0)
    ax.axvline(-limit_val, color="#59A14F", ls="--", lw=0.8, alpha=0.8)
    ax.axvline(limit_val, color="#59A14F", ls="--", lw=0.8, alpha=0.8)


def _make_grouped_feature_space_multicase_plot(
    df: pd.DataFrame,
    *,
    selected_feature_cols: list[str],
    n_cases: int,
    random_seed: int,
    out_path: Path | None = None,
) -> dict[str, object]:
    dd = load_distance_definition(selected_feature_cols) if selected_feature_cols else {"available": False}
    dd_group_weights = dd.get("group_weights", {}) if isinstance(dd, dict) else {}
    if not isinstance(dd_group_weights, dict):
        dd_group_weights = {}
    dd_feature_groups = dd.get("feature_groups", {}) if isinstance(dd, dict) else {}
    if not isinstance(dd_feature_groups, dict):
        dd_feature_groups = {}

    hist_cfg = dd_feature_groups.get("rate_histogram", {})
    if not isinstance(hist_cfg, dict):
        hist_cfg = {}
    hist_active = (not dd_group_weights) or float(dd_group_weights.get("rate_histogram", 0.0)) > 0.0
    hist_cols = [
        str(col)
        for col in hist_cfg.get("feature_columns", [])
        if str(col) in df.columns
    ]
    if not hist_cols and hist_active:
        hist_cols = sorted(
            [str(c) for c in df.columns if HIST_RATE_COLUMN_RE.match(str(c))],
            key=lambda c: int(HIST_RATE_COLUMN_RE.match(str(c)).group("bin")) if HIST_RATE_COLUMN_RE.match(str(c)) else 0,
        )

    eff_cfg = dd_feature_groups.get("efficiency_vectors", {})
    if not isinstance(eff_cfg, dict):
        eff_cfg = {}
    eff_active = (not dd_group_weights) or float(dd_group_weights.get("efficiency_vectors", 0.0)) > 0.0
    eff_payloads: list[dict[str, object]] = []
    if eff_active:
        eff_payloads = _prepare_efficiency_vector_group_payloads(dict_df=df, data_df=df)
        eff_payloads = _filter_efficiency_vector_payloads(
            eff_payloads,
            feature_groups_cfg=eff_cfg if eff_cfg else None,
            selected_feature_columns=selected_feature_cols,
        )

    axis_payloads: dict[str, list[dict[str, object]]] = {"x": [], "y": [], "theta": []}
    for payload in eff_payloads:
        axis_name = str(payload.get("axis", "")).strip().lower()
        if axis_name in axis_payloads:
            axis_payloads[axis_name].append(payload)

    sampled_rows = _select_grouped_multicase_rows(
        df,
        n_cases=int(n_cases),
        random_seed=int(random_seed),
    )
    summary: dict[str, object] = {
        "status": "unavailable",
        "sampled_row_indices": sampled_rows.tolist(),
        "n_sampled_cases": int(sampled_rows.size),
        "rate_histogram_bins_used": int(len(hist_cols)),
        "efficiency_vector_groups_used": int(len(eff_payloads)),
    }
    if sampled_rows.size == 0:
        return summary

    plot_path = out_path or (PLOTS_DIR / "feature_grouped_multicase.png")
    fig = plt.figure(figsize=(15.5, 15.5), constrained_layout=True)
    gs = fig.add_gridspec(5, 3, height_ratios=[1.2, 1.0, 1.0, 1.0, 1.0], hspace=0.25, wspace=0.20)
    sampled_flux = None
    if "flux_cm2_min" in df.columns:
        sampled_flux = pd.to_numeric(df.iloc[sampled_rows]["flux_cm2_min"], errors="coerce").to_numpy(dtype=float)
    colors = plt.cm.viridis(np.linspace(0.05, 0.95, sampled_rows.size))

    if hist_cols:
        ax_hist = fig.add_subplot(gs[0, :])
        bins = np.asarray(
            [int(HIST_RATE_COLUMN_RE.match(col).group("bin")) for col in hist_cols],
            dtype=float,
        )
        hist_frame = df[hist_cols].apply(pd.to_numeric, errors="coerce")
        sample_hist = hist_frame.iloc[sampled_rows].to_numpy(dtype=float)
        for idx, curve in enumerate(sample_hist):
            if not np.isfinite(curve).any():
                continue
            ax_hist.plot(bins, curve, color=colors[idx], alpha=0.55, lw=1.0)
        hist_med = hist_frame.median(axis=0, skipna=True).to_numpy(dtype=float)
        if np.isfinite(hist_med).any():
            ax_hist.plot(bins, hist_med, color="black", lw=2.0, label="Global median")
        ax_hist.set_xlabel("Rate-histogram bin index", fontsize=8)
        ax_hist.set_ylabel("Rate [Hz]", fontsize=8)
        ax_hist.set_title(f"Rate histogram: {sampled_rows.size} sampled transformed rows", fontsize=10)
        ax_hist.grid(True, alpha=0.18)
        if sampled_flux is not None and np.isfinite(sampled_flux).any():
            flux_min = float(np.nanmin(sampled_flux))
            flux_max = float(np.nanmax(sampled_flux))
            ax_hist.text(
                0.01,
                0.98,
                f"Sampled by flux spread\nflux range [{flux_min:.3g}, {flux_max:.3g}]",
                transform=ax_hist.transAxes,
                ha="left",
                va="top",
                fontsize=8,
                bbox=dict(boxstyle="round,pad=0.25", facecolor="white", alpha=0.8),
            )
        else:
            ax_hist.text(
                0.01,
                0.98,
                f"{sampled_rows.size} sampled rows",
                transform=ax_hist.transAxes,
                ha="left",
                va="top",
                fontsize=8,
                bbox=dict(boxstyle="round,pad=0.25", facecolor="white", alpha=0.8),
            )

    plane_colors = {
        1: "#1F77B4",
        2: "#FF7F0E",
        3: "#2CA02C",
        4: "#D62728",
    }
    fiducial = {}
    if isinstance(eff_cfg.get("fiducial"), dict):
        fiducial = dict(eff_cfg.get("fiducial", {}))

    for plane in range(1, 5):
        for axis_idx, axis_name in enumerate(("x", "y", "theta")):
            ax = fig.add_subplot(gs[plane, axis_idx])
            payload = next(
                (
                    item
                    for item in axis_payloads.get(axis_name, [])
                    if int(item.get("plane", 0)) == plane
                ),
                None,
            )
            if payload is None:
                ax.axis("off")
                continue
            centers = np.asarray(payload.get("centers", []), dtype=float)
            eff_mat = np.asarray(payload.get("dict_eff", []), dtype=float)
            if centers.size == 0 or eff_mat.ndim != 2:
                ax.axis("off")
                continue
            eff_sample = eff_mat[sampled_rows]
            _apply_grouped_fiducial_overlay(ax, axis_name=axis_name, fiducial=fiducial)
            for idx, curve in enumerate(eff_sample):
                valid = np.isfinite(centers) & np.isfinite(curve)
                if not np.any(valid):
                    continue
                ax.plot(centers[valid], curve[valid], color=colors[idx], alpha=0.50, lw=0.9)
            eff_med = np.nanmedian(eff_mat, axis=0)
            valid_med = np.isfinite(centers) & np.isfinite(eff_med)
            if np.any(valid_med):
                ax.plot(
                    centers[valid_med],
                    eff_med[valid_med],
                    color=plane_colors.get(plane, "black"),
                    lw=1.8,
                    alpha=0.95,
                )
            axis_label = {
                "x": "Projected X [mm]",
                "y": "Projected Y [mm]",
                "theta": "Theta [deg]",
            }.get(axis_name, axis_name)
            ax.set_xlabel(axis_label, fontsize=8)
            ax.set_ylabel("Efficiency", fontsize=8)
            ax.set_ylim(0.0, 1.05)
            ax.set_title(f"Plane {plane} vs {axis_name}", fontsize=9)
            ax.grid(True, alpha=0.18)
            ax.tick_params(labelsize=7)

    fig.suptitle(
        f"STEP 1.2 grouped feature-space sampled cases ({sampled_rows.size} rows) with fiducial overlays",
        fontsize=12,
        y=0.995,
    )
    _save_figure(fig, plot_path, dpi=150)
    plt.close(fig)
    summary["status"] = "ok"
    return summary


def _plot_feature_space_regions(
    df: pd.DataFrame,
    *,
    pairs: list[tuple[str, str]],
    zoom_quantiles: tuple[float, float],
    sample_max_rows: int,
    random_seed: int,
) -> None:
    valid_pairs = [(x, y) for x, y in pairs if x in df.columns and y in df.columns]
    if not valid_pairs:
        return

    plot_df = df
    if sample_max_rows > 0 and len(plot_df) > sample_max_rows:
        plot_df = plot_df.sample(n=sample_max_rows, random_state=random_seed)

    n_rows = len(valid_pairs)
    fig, axes = plt.subplots(
        n_rows,
        2,
        figsize=(12.0, 3.8 * n_rows),
        squeeze=False,
    )
    q_low, q_high = zoom_quantiles
    for r, (x_col, y_col) in enumerate(valid_pairs):
        x = pd.to_numeric(plot_df[x_col], errors="coerce")
        y = pd.to_numeric(plot_df[y_col], errors="coerce")
        mask = x.notna() & y.notna()
        if not bool(mask.any()):
            axes[r, 0].set_visible(False)
            axes[r, 1].set_visible(False)
            continue
        xv = x.loc[mask].to_numpy(dtype=float)
        yv = y.loc[mask].to_numpy(dtype=float)

        ax_full = axes[r, 0]
        ax_full.hexbin(xv, yv, gridsize=55, mincnt=1, cmap="viridis")
        ax_full.set_xlabel(x_col)
        ax_full.set_ylabel(y_col)
        ax_full.set_title("Full range")
        ax_full.grid(True, alpha=0.2)

        ax_zoom = axes[r, 1]
        x_q0 = float(np.nanquantile(xv, q_low))
        x_q1 = float(np.nanquantile(xv, q_high))
        y_q0 = float(np.nanquantile(yv, q_low))
        y_q1 = float(np.nanquantile(yv, q_high))
        zmask = (xv >= x_q0) & (xv <= x_q1) & (yv >= y_q0) & (yv <= y_q1)
        if bool(np.any(zmask)):
            zx = xv[zmask]
            zy = yv[zmask]
        else:
            zx = xv
            zy = yv
        ax_zoom.hexbin(zx, zy, gridsize=45, mincnt=1, cmap="viridis")
        ax_zoom.set_xlabel(x_col)
        ax_zoom.set_ylabel(y_col)
        ax_zoom.set_title(f"Central region [{q_low:.0%}, {q_high:.0%}]")
        ax_zoom.grid(True, alpha=0.2)

    fig.suptitle("STEP 1.2 feature-space regions", y=0.995, fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.985])
    _save_figure(fig, PLOTS_DIR / "feature_space_regions.png", dpi=150)
    plt.close(fig)


def _plot_global_rate_prefix_overview(
    df: pd.DataFrame,
    *,
    rate_col_by_prefix: dict[str, str],
) -> None:
    if not rate_col_by_prefix:
        return
    cols = [rate_col_by_prefix[p] for p in sorted(rate_col_by_prefix.keys()) if rate_col_by_prefix[p] in df.columns]
    if not cols:
        return
    sample_cols = cols[:8]
    fig, ax = plt.subplots(figsize=(10.5, 4.8))
    values = [pd.to_numeric(df[c], errors="coerce").dropna().to_numpy(dtype=float) for c in sample_cols]
    labels = [c.replace("events_per_second_global_rate_", "") for c in sample_cols]
    non_empty_vals = [v for v in values if v.size > 0]
    if not non_empty_vals:
        plt.close(fig)
        return
    ax.boxplot(
        [v if v.size > 0 else np.asarray([np.nan]) for v in values],
        tick_labels=labels,
        showfliers=False,
    )
    ax.set_ylabel("Global rate [Hz]")
    ax.set_title("Per-prefix global-rate overview (STEP 1.2 transform)")
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    _save_figure(fig, PLOTS_DIR / "global_rate_prefix_overview.png", dpi=150)
    plt.close(fig)


def _plot_efficiency_scalar_controls(
    df: pd.DataFrame,
    *,
    sample_max_rows: int,
    random_seed: int,
) -> dict[str, object]:
    sim_cols = [f"eff_sim_{plane}" for plane in (1, 2, 3, 4) if f"eff_sim_{plane}" in df.columns]
    emp_cols = [f"eff_empirical_{plane}" for plane in (1, 2, 3, 4) if f"eff_empirical_{plane}" in df.columns]
    info: dict[str, object] = {
        "status": "skipped",
        "simulated_efficiency_columns": sim_cols,
        "empirical_efficiency_columns": emp_cols,
        "planes_with_both_simulated_and_empirical": [],
        "rows_with_complete_plane_aggregate": 0,
    }
    if not sim_cols and not emp_cols:
        info["reason"] = "no_efficiency_scalar_columns"
        return info

    work = df.copy()
    scatter_cap = int(sample_max_rows) if sample_max_rows > 0 else len(work)
    if scatter_cap > 0:
        scatter_cap = min(scatter_cap, 6000)
        if len(work) > scatter_cap:
            work = work.sample(n=scatter_cap, random_state=random_seed)

    sim_df = work[sim_cols].apply(pd.to_numeric, errors="coerce") if sim_cols else pd.DataFrame(index=work.index)
    emp_df = work[emp_cols].apply(pd.to_numeric, errors="coerce") if emp_cols else pd.DataFrame(index=work.index)
    valid_sim_cols = [col for col in sim_cols if col in sim_df.columns and sim_df[col].notna().any()]
    valid_emp_cols = [col for col in emp_cols if col in emp_df.columns and emp_df[col].notna().any()]
    common_planes = [
        plane
        for plane in (1, 2, 3, 4)
        if f"eff_sim_{plane}" in valid_sim_cols and f"eff_empirical_{plane}" in valid_emp_cols
    ]
    info["simulated_efficiency_columns"] = valid_sim_cols
    info["empirical_efficiency_columns"] = valid_emp_cols
    info["planes_with_both_simulated_and_empirical"] = common_planes
    if not valid_sim_cols and not valid_emp_cols:
        info["reason"] = "all_efficiency_scalar_columns_empty"
        return info

    fig, axes = plt.subplots(2, 3, figsize=(17.0, 9.8), squeeze=False)
    plane_colors = {
        1: "#4C78A8",
        2: "#F58518",
        3: "#54A24B",
        4: "#E45756",
    }

    ax = axes[0, 0]
    sim_arrays = [
        sim_df[col].dropna().to_numpy(dtype=float)
        for col in valid_sim_cols
        if sim_df[col].notna().any()
    ]
    if sim_arrays:
        sim_labels = [f"P{col.split('_')[-1]}" for col in valid_sim_cols if sim_df[col].notna().any()]
        bp = ax.boxplot(sim_arrays, tick_labels=sim_labels, showfliers=False, patch_artist=True)
        for patch, label in zip(bp["boxes"], sim_labels):
            plane = int(label[1:])
            patch.set_facecolor(plane_colors.get(plane, "#4C78A8"))
            patch.set_alpha(0.5)
        ax.set_ylim(0.0, 1.05)
        ax.set_ylabel("Simulated efficiency")
        ax.set_title("Per-plane simulated efficiencies")
        ax.grid(True, alpha=0.2)
    else:
        ax.text(0.5, 0.5, "No simulated efficiency scalars", ha="center", va="center", transform=ax.transAxes)
        ax.set_axis_off()

    ax = axes[0, 1]
    emp_arrays = [
        emp_df[col].dropna().to_numpy(dtype=float)
        for col in valid_emp_cols
        if emp_df[col].notna().any()
    ]
    if emp_arrays:
        emp_labels = [f"P{col.split('_')[-1]}" for col in valid_emp_cols if emp_df[col].notna().any()]
        bp = ax.boxplot(emp_arrays, tick_labels=emp_labels, showfliers=False, patch_artist=True)
        for patch, label in zip(bp["boxes"], emp_labels):
            plane = int(label[1:])
            patch.set_facecolor(plane_colors.get(plane, "#4C78A8"))
            patch.set_alpha(0.5)
        ax.set_ylim(0.0, 1.05)
        ax.set_ylabel("Empirical efficiency")
        ax.set_title("Per-plane empirical efficiencies")
        ax.grid(True, alpha=0.2)
    else:
        ax.text(0.5, 0.5, "No empirical efficiency scalars", ha="center", va="center", transform=ax.transAxes)
        ax.set_axis_off()

    ax = axes[0, 2]
    spread_series: list[np.ndarray] = []
    spread_labels: list[str] = []
    if len(valid_sim_cols) >= 2:
        sim_spread = sim_df[valid_sim_cols].max(axis=1) - sim_df[valid_sim_cols].min(axis=1)
        sim_spread = sim_spread[np.isfinite(sim_spread.to_numpy(dtype=float))].to_numpy(dtype=float)
        if sim_spread.size > 0:
            spread_series.append(sim_spread)
            spread_labels.append("simulated")
    if len(valid_emp_cols) >= 2:
        emp_spread = emp_df[valid_emp_cols].max(axis=1) - emp_df[valid_emp_cols].min(axis=1)
        emp_spread = emp_spread[np.isfinite(emp_spread.to_numpy(dtype=float))].to_numpy(dtype=float)
        if emp_spread.size > 0:
            spread_series.append(emp_spread)
            spread_labels.append("empirical")
    if spread_series:
        spread_hi = max(float(np.nanpercentile(vals, 99.0)) for vals in spread_series if vals.size > 0)
        if not np.isfinite(spread_hi) or spread_hi <= 0.0:
            spread_hi = 0.1
        bins = np.linspace(0.0, spread_hi, 35)
        colors = {"simulated": "#4C78A8", "empirical": "#E45756"}
        for vals, label in zip(spread_series, spread_labels):
            ax.hist(vals, bins=bins, alpha=0.5, label=label, color=colors.get(label, "#4C78A8"))
        ax.set_xlabel("Plane-to-plane spread")
        ax.set_ylabel("Rows")
        ax.set_title("Scalar efficiency spread across planes")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.2)
    else:
        ax.text(0.5, 0.5, "Need at least two valid plane scalars", ha="center", va="center", transform=ax.transAxes)
        ax.set_axis_off()

    ax = axes[1, 0]
    if common_planes:
        for plane in common_planes:
            x = emp_df[f"eff_empirical_{plane}"]
            y = sim_df[f"eff_sim_{plane}"]
            mask = x.notna() & y.notna()
            if not bool(mask.any()):
                continue
            ax.scatter(
                x.loc[mask].to_numpy(dtype=float),
                y.loc[mask].to_numpy(dtype=float),
                s=10,
                alpha=0.28,
                color=plane_colors.get(plane, "#4C78A8"),
                edgecolors="none",
                label=f"P{plane}",
                rasterized=True,
            )
        ax.plot([0.0, 1.0], [0.0, 1.0], color="black", linestyle="--", linewidth=1.0)
        ax.set_xlim(0.0, 1.0)
        ax.set_ylim(0.0, 1.0)
        ax.set_aspect("equal", adjustable="box")
        ax.set_xlabel("Empirical efficiency")
        ax.set_ylabel("Simulated efficiency")
        ax.set_title("Plane-wise empirical vs simulated")
        ax.legend(fontsize=8, loc="lower right")
        ax.grid(True, alpha=0.2)
    else:
        ax.text(0.5, 0.5, "No common empirical/simulated plane scalars", ha="center", va="center", transform=ax.transAxes)
        ax.set_axis_off()

    aggregate_plane_cols_sim = [f"eff_sim_{plane}" for plane in common_planes]
    aggregate_plane_cols_emp = [f"eff_empirical_{plane}" for plane in common_planes]
    complete_mask = pd.Series(False, index=work.index, dtype=bool)
    if aggregate_plane_cols_sim and aggregate_plane_cols_emp:
        complete_mask = (
            sim_df[aggregate_plane_cols_sim].notna().all(axis=1)
            & emp_df[aggregate_plane_cols_emp].notna().all(axis=1)
        )
    info["rows_with_complete_plane_aggregate"] = int(complete_mask.sum())
    agg_label = f"{len(common_planes)}-plane" if common_planes else "aggregate"

    ax = axes[1, 1]
    if bool(complete_mask.any()):
        mean_emp = emp_df.loc[complete_mask, aggregate_plane_cols_emp].mean(axis=1).to_numpy(dtype=float)
        mean_sim = sim_df.loc[complete_mask, aggregate_plane_cols_sim].mean(axis=1).to_numpy(dtype=float)
        ax.scatter(mean_emp, mean_sim, s=10, alpha=0.28, color="#4C78A8", edgecolors="none", rasterized=True)
        ax.plot([0.0, 1.0], [0.0, 1.0], color="black", linestyle="--", linewidth=1.0)
        ax.set_xlim(0.0, 1.0)
        ax.set_ylim(0.0, 1.0)
        ax.set_aspect("equal", adjustable="box")
        ax.set_xlabel(f"{agg_label} mean empirical efficiency")
        ax.set_ylabel(f"{agg_label} mean simulated efficiency")
        ax.set_title(f"{agg_label} mean efficiency consistency")
        ax.grid(True, alpha=0.2)
        mae = float(np.mean(np.abs(mean_sim - mean_emp))) if mean_emp.size else float("nan")
        ax.text(
            0.03,
            0.97,
            f"N={mean_emp.size}\nMAE={mae:.3f}",
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontsize=8,
            bbox={"facecolor": "white", "alpha": 0.8, "edgecolor": "none"},
        )
    else:
        ax.text(0.5, 0.5, "No complete rows for aggregate mean", ha="center", va="center", transform=ax.transAxes)
        ax.set_axis_off()

    ax = axes[1, 2]
    if bool(complete_mask.any()):
        prod_emp = emp_df.loc[complete_mask, aggregate_plane_cols_emp].prod(axis=1).to_numpy(dtype=float)
        prod_sim = sim_df.loc[complete_mask, aggregate_plane_cols_sim].prod(axis=1).to_numpy(dtype=float)
        ax.scatter(prod_emp, prod_sim, s=10, alpha=0.28, color="#E45756", edgecolors="none", rasterized=True)
        ax.plot([0.0, 1.0], [0.0, 1.0], color="black", linestyle="--", linewidth=1.0)
        prod_hi = max(0.05, float(np.nanmax(np.concatenate([prod_emp, prod_sim]))))
        prod_hi = min(1.0, max(prod_hi * 1.05, 0.05))
        ax.set_xlim(0.0, prod_hi)
        ax.set_ylim(0.0, prod_hi)
        ax.set_aspect("equal", adjustable="box")
        ax.set_xlabel(f"{agg_label} product empirical efficiency")
        ax.set_ylabel(f"{agg_label} product simulated efficiency")
        ax.set_title(f"{agg_label} efficiency-product consistency")
        ax.grid(True, alpha=0.2)
        mae = float(np.mean(np.abs(prod_sim - prod_emp))) if prod_emp.size else float("nan")
        ax.text(
            0.03,
            0.97,
            f"N={prod_emp.size}\nMAE={mae:.3f}",
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontsize=8,
            bbox={"facecolor": "white", "alpha": 0.8, "edgecolor": "none"},
        )
    else:
        ax.text(0.5, 0.5, "No complete rows for aggregate product", ha="center", va="center", transform=ax.transAxes)
        ax.set_axis_off()

    fig.suptitle(
        "STEP 1.2 efficiency scalar controls\nEmpirical efficiencies from TT-count ratios; simulated efficiencies from parameter space",
        y=0.995,
        fontsize=12,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.965])
    _save_figure(fig, PLOTS_DIR / "efficiency_scalar_controls.png", dpi=150)
    plt.close(fig)
    info["status"] = "ok"
    return info


def _plot_task4_efficiency_scalar_vs_sim_controls(
    df: pd.DataFrame,
    *,
    sample_max_rows: int,
    random_seed: int,
) -> dict[str, object]:
    def _save_placeholder(message: str) -> None:
        fig, ax = plt.subplots(figsize=(8.5, 4.8))
        ax.text(
            0.5,
            0.55,
            message,
            ha="center",
            va="center",
            transform=ax.transAxes,
            fontsize=11,
        )
        ax.text(
            0.5,
            0.28,
            "Expected columns: efficiency_scalar_p{plane}_{x|y|theta}_fiducial_eff\n"
            "Current STEP 1.2 run can only compare them after Task 4 metadata is regenerated and STEP 1.1 is rerun.",
            ha="center",
            va="center",
            transform=ax.transAxes,
            fontsize=9,
        )
        ax.set_axis_off()
        fig.suptitle(
            "STEP 1.2 Task 4 scalar-efficiency controls",
            y=0.98,
            fontsize=12,
        )
        fig.tight_layout(rect=[0, 0, 1, 0.95])
        _save_figure(fig, PLOTS_DIR / "task4_efficiency_scalar_vs_sim_controls.png", dpi=150)
        plt.close(fig)

    axes_order = ("x", "y", "theta")
    info: dict[str, object] = {
        "status": "skipped",
        "axes_considered": list(axes_order),
        "planes_with_any_task4_scalar": [],
        "available_task4_scalar_columns": [],
        "available_simulated_efficiency_columns": [],
        "panel_count_with_data": 0,
    }

    sim_cols = {
        plane: f"eff_sim_{plane}"
        for plane in (1, 2, 3, 4)
        if f"eff_sim_{plane}" in df.columns
    }
    if not sim_cols:
        info["reason"] = "missing_eff_sim_columns"
        _save_placeholder("Missing simulated efficiency columns in STEP 1.2 input.")
        return info
    info["available_simulated_efficiency_columns"] = list(sim_cols.values())

    scalar_map: dict[tuple[str, int], str] = {}
    for axis_name in axes_order:
        for plane in (1, 2, 3, 4):
            col = f"efficiency_scalar_p{plane}_{axis_name}_fiducial_eff"
            if col in df.columns:
                scalar_map[(axis_name, plane)] = col

    if not scalar_map:
        info["reason"] = "missing_task4_scalar_efficiency_columns"
        _save_placeholder("Task 4 scalar-efficiency metadata columns are not present in the current STEP 1.2 input.")
        return info

    info["available_task4_scalar_columns"] = [scalar_map[key] for key in sorted(scalar_map)]
    info["planes_with_any_task4_scalar"] = sorted({plane for (_, plane) in scalar_map})

    work = df.copy()
    scatter_cap = int(sample_max_rows) if sample_max_rows > 0 else len(work)
    if scatter_cap > 0:
        scatter_cap = min(scatter_cap, 6000)
        if len(work) > scatter_cap:
            work = work.sample(n=scatter_cap, random_state=random_seed)

    fig, axes = plt.subplots(3, 4, figsize=(16.0, 11.5), squeeze=False)
    plane_colors = {
        1: "#4C78A8",
        2: "#F58518",
        3: "#54A24B",
        4: "#E45756",
    }
    axis_titles = {
        "x": "Projected X scalar",
        "y": "Projected Y scalar",
        "theta": "Theta=0 scalar",
    }

    panel_count = 0
    for row_idx, axis_name in enumerate(axes_order):
        for col_idx, plane in enumerate((1, 2, 3, 4)):
            ax = axes[row_idx, col_idx]
            scalar_col = scalar_map.get((axis_name, plane))
            sim_col = sim_cols.get(plane)
            if scalar_col is None or sim_col is None:
                ax.text(
                    0.5,
                    0.5,
                    "Not available",
                    ha="center",
                    va="center",
                    transform=ax.transAxes,
                    fontsize=9,
                )
                ax.set_axis_off()
                continue

            x = pd.to_numeric(work[scalar_col], errors="coerce")
            y = pd.to_numeric(work[sim_col], errors="coerce")
            mask = x.notna() & y.notna()
            if not bool(mask.any()):
                ax.text(
                    0.5,
                    0.5,
                    "No finite rows",
                    ha="center",
                    va="center",
                    transform=ax.transAxes,
                    fontsize=9,
                )
                ax.set_axis_off()
                continue

            xv = x.loc[mask].to_numpy(dtype=float)
            yv = y.loc[mask].to_numpy(dtype=float)
            ax.scatter(
                xv,
                yv,
                s=10,
                alpha=0.28,
                color=plane_colors.get(plane, "#4C78A8"),
                edgecolors="none",
                rasterized=True,
            )
            ax.plot([0.0, 1.0], [0.0, 1.0], color="black", linestyle="--", linewidth=1.0)
            ax.set_xlim(0.0, 1.0)
            ax.set_ylim(0.0, 1.0)
            ax.set_aspect("equal", adjustable="box")
            if row_idx == len(axes_order) - 1:
                ax.set_xlabel(f"{axis_titles[axis_name]}")
            else:
                ax.set_xlabel("")
            if col_idx == 0:
                ax.set_ylabel("Simulated efficiency")
            else:
                ax.set_ylabel("")
            mae = float(np.mean(np.abs(yv - xv))) if xv.size else float("nan")
            ax.set_title(f"P{plane} {axis_name}", fontsize=10)
            ax.text(
                0.03,
                0.97,
                f"N={xv.size}\nMAE={mae:.3f}",
                transform=ax.transAxes,
                ha="left",
                va="top",
                fontsize=8,
                bbox={"facecolor": "white", "alpha": 0.8, "edgecolor": "none"},
            )
            ax.grid(True, alpha=0.2)
            panel_count += 1

    fig.suptitle(
        "STEP 1.2 Task 4 scalar-efficiency controls\nTask 4 projected X/Y/theta scalar summaries vs simulated plane efficiencies",
        y=0.995,
        fontsize=12,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.965])
    _save_figure(fig, PLOTS_DIR / "task4_efficiency_scalar_vs_sim_controls.png", dpi=150)
    plt.close(fig)

    info["status"] = "ok"
    info["panel_count_with_data"] = int(panel_count)
    return info


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Step 1.2: Transform expanded feature space."
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--input-csv", default=None)
    args = parser.parse_args()

    config = _load_config(Path(args.config))
    _clear_plots_dir()
    cfg_12 = config.get("step_1_2", {}) if isinstance(config, dict) else {}
    cfg_14 = config.get("step_1_4", {}) if isinstance(config, dict) else {}
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
    derived_columns_catalog = _normalize_derived_columns_catalog(
        feature_space_cfg.get("derived_columns_catalog")
        if isinstance(feature_space_cfg, Mapping)
        else None
    )
    transform_options = resolve_feature_space_transform_options(
        feature_space_cfg=feature_space_cfg,
        default_tt_prefix_priority=CANONICAL_PREFIX_PRIORITY,
    )
    column_transform_cfg = _resolve_column_transformations(
        feature_space_cfg=feature_space_cfg if isinstance(feature_space_cfg, Mapping) else {},
    )
    transform_options = dict(transform_options)
    transform_options["column_transformations"] = bool(column_transform_cfg.get("enabled", False))
    post_tt_aggregate_cfg = _resolve_post_tt_plane_aggregate_config(
        feature_space_cfg=feature_space_cfg if isinstance(feature_space_cfg, Mapping) else {},
    )
    preferred_prefixes_t = tuple(transform_options["tt_prefix_priority"])
    requested_keep_patterns = _normalize_requested_columns(
        cfg_12.get("transform_keep_columns")
    )
    required_passthrough_cols = _resolve_required_passthrough_columns(
        cfg_12 if isinstance(cfg_12, Mapping) else {},
    )
    if (
        not requested_keep_patterns
        and not feature_space_cfg.get("materialized_columns")
        and not column_transform_cfg.get("enabled", False)
    ):
        log.error(
            "STEP 1.2 requires keep_dimensions in config_step_1.2_feature_space.json (step_1_2.kept), "
            "step_1_2.materialized_columns, or step_1_2.transform_keep_columns in config."
        )
        return 1

    try:
        sample_max_rows = int(
            cfg_12.get(
                "parameter_matrix_plot_sample_max_rows",
                cfg_12.get("feature_space_plot_sample_max_rows", 25000),
            )
        )
    except (TypeError, ValueError):
        sample_max_rows = 25000
    sample_max_rows = max(0, sample_max_rows)
    try:
        plot_seed = int(
            cfg_12.get(
                "parameter_matrix_plot_random_seed",
                cfg_12.get("feature_space_plot_random_seed", 1234),
            )
        )
    except (TypeError, ValueError):
        plot_seed = 1234
    include_rate_histogram_in_feature_matrix = str(
        cfg_12.get("feature_matrix_plot_include_rate_histogram", True)
    ).strip().lower() not in {"0", "false", "no", "off"}
    include_efficiency_vectors_in_feature_matrix = str(
        cfg_12.get("feature_matrix_plot_include_efficiency_vectors", True)
    ).strip().lower() not in {"0", "false", "no", "off"}
    feature_space_plot_suppressed_patterns = _resolve_feature_space_plot_suppression_patterns(
        config,
        step_cfg=cfg_12 if isinstance(cfg_12, Mapping) else {},
    )
    try:
        feature_scatter_matrix_max_side = int(cfg_12.get("feature_scatter_matrix_max_side", 15))
    except (TypeError, ValueError):
        feature_scatter_matrix_max_side = 15
    feature_scatter_matrix_max_side = max(feature_scatter_matrix_max_side, 2)

    input_path = Path(args.input_csv).expanduser() if args.input_csv else DEFAULT_INPUT
    if not input_path.exists():
        log.error("Input CSV not found: %s", input_path)
        return 1

    log.info("Loading expanded feature-space data: %s", input_path)
    df = pd.read_csv(input_path, low_memory=False)
    df = _ensure_efficiency_columns(df)
    log.info("  Rows loaded: %d, columns=%d", len(df), len(df.columns))
    if feature_space_cfg:
        log.info("Feature-space config: %s", feature_space_config_path)
    if derived_columns_catalog:
        log.info("STEP 1.2 derived-column catalog (%d entries):", len(derived_columns_catalog))
        for entry in derived_columns_catalog:
            source_text = str(entry.get("source", "")).strip()
            if source_text:
                log.info("  %s <= %s", entry["column_pattern"], source_text)
            else:
                log.info("  %s", entry["column_pattern"])

    try:
        min_eff_sim = float(cfg_12.get("min_simulated_efficiency", 0.5))
    except (TypeError, ValueError):
        min_eff_sim = 0.5

    out, rate_col_by_prefix, tt_cols_by_prefix = _build_prefix_global_rate_columns(df)
    out, added_standard_rate_cols = _ensure_standard_task_prefix_rate_columns(
        out,
        rate_col_by_prefix=rate_col_by_prefix,
    )
    canonical_source_counts: dict[str, int] = {}
    if transform_options["derive_canonical_global_rate"]:
        out, canonical_source_counts = _select_canonical_global_rate(
            out,
            rate_col_by_prefix=rate_col_by_prefix,
            preferred_prefixes=preferred_prefixes_t,
        )
    empirical_selected_prefix = None
    empirical_used_prefixes: list[str] = []
    if transform_options["derive_empirical_efficiencies"]:
        out, empirical_selected_prefix, empirical_used_prefixes = _compute_empirical_efficiencies(
            out,
            preferred_prefixes=preferred_prefixes_t,
        )
    helper_count = 0
    if transform_options["derive_physics_helpers"]:
        out, helper_count = _add_derived_physics_helper_columns(
            out,
        )
    post_tt_plane_aggregates_info: dict[str, object] = {
        "enabled": False,
        "source_prefix": str(post_tt_aggregate_cfg.get("source_prefix", "post_tt")),
        "columns": {},
    }
    if (
        bool(transform_options.get("derive_post_tt_plane_aggregates", False))
        and bool(post_tt_aggregate_cfg.get("enabled", True))
    ):
        out, post_tt_plane_aggregates_info = _add_post_tt_plane_aggregate_columns(
            out,
            aggregate_cfg=post_tt_aggregate_cfg,
        )
        n_targets = int(len(post_tt_plane_aggregates_info.get("columns", {})))
        log.info(
            "Derived post_tt aggregate features: %d column(s) from prefix '%s'.",
            n_targets,
            post_tt_plane_aggregates_info.get("source_prefix", "post_tt"),
        )
    # Filter: keep only rows where all simulated efficiencies exceed a threshold.
    eff_sim_cols = [c for c in ("eff_sim_1", "eff_sim_2", "eff_sim_3", "eff_sim_4") if c in out.columns]
    if eff_sim_cols and min_eff_sim > 0.0:
        eff_vals = out[eff_sim_cols].apply(pd.to_numeric, errors="coerce")
        keep_mask = (eff_vals >= min_eff_sim).all(axis=1)
        n_before = len(out)
        out = out.loc[keep_mask].reset_index(drop=True)
        log.info(
            "Simulated-efficiency filter (>= %.2f on %s): kept %d / %d rows (removed %d).",
            min_eff_sim, eff_sim_cols, len(out), n_before, n_before - len(out),
        )

    # Filter: keep only rows where the spread (max - min) of eff_sim is below a threshold.
    try:
        max_eff_spread = float(cfg_12.get("max_simulated_efficiency_spread", 0.15))
    except (TypeError, ValueError):
        max_eff_spread = 0.15
    if eff_sim_cols and max_eff_spread > 0.0:
        eff_vals = out[eff_sim_cols].apply(pd.to_numeric, errors="coerce")
        spread = eff_vals.max(axis=1) - eff_vals.min(axis=1)
        keep_mask = spread <= max_eff_spread
        n_before = len(out)
        out = out.loc[keep_mask].reset_index(drop=True)
        log.info(
            "Simulated-efficiency spread filter (<= %.2f on %s): kept %d / %d rows (removed %d).",
            max_eff_spread, eff_sim_cols, len(out), n_before, n_before - len(out),
        )

    efficiency_scalar_control_info = _plot_efficiency_scalar_controls(
        out,
        sample_max_rows=sample_max_rows,
        random_seed=plot_seed,
    )
    task4_efficiency_scalar_control_info = _plot_task4_efficiency_scalar_vs_sim_controls(
        out,
        sample_max_rows=sample_max_rows,
        random_seed=plot_seed,
    )

    column_transform_info: dict[str, object] = {"enabled": False}
    if column_transform_cfg.get("enabled", False):
        try:
            out, column_transform_info, missing_keep = _apply_column_transformations(
                out,
                transform_cfg=column_transform_cfg,
            )
        except Exception as exc:
            log.error("STEP 1.2 column transformations failed: %s", exc)
            return 1
        if missing_keep:
            log.error(
                "STEP 1.2 keep_dimensions missing from dataset after transformations: %s",
                missing_keep,
            )
            return 1
        log.info(
            "Applied column transformations: defined %d new dimension(s); keep_dimensions=%d, required_passthrough_columns=%d.",
            len(column_transform_info.get("new_dimensions", {})),
            len(column_transform_info.get("final_keep_dimensions", [])),
            len(required_passthrough_cols),
        )

    (
        derived_catalog_pre_curation_presence,
        derived_catalog_pre_curation_unmatched,
    ) = _catalog_presence_against_columns(
        catalog_entries=derived_columns_catalog,
        available_columns=list(out.columns),
        transform_options=transform_options,
    )
    if derived_catalog_pre_curation_unmatched:
        log.warning(
            "Derived-column catalog entries without matches before curation: %s",
            derived_catalog_pre_curation_unmatched,
        )

    materialized_cols_info: dict[str, object]
    unmatched_keep_patterns: list[str]
    unmatched_keep_exclude_patterns: list[str]
    missing_required_passthrough_cols: list[str]
    if column_transform_cfg.get("enabled", False):
        curated_cols, missing_required_passthrough_cols = _merge_materialized_with_required_columns(
            materialized_columns=list(column_transform_info.get("final_keep_dimensions", [])),
            required_columns=required_passthrough_cols,
            available_columns=list(out.columns),
        )
        materialized_cols_info = {
            "source": "step_1_2.column_transformations.keep_dimensions_plus_runtime_passthrough",
            "include_patterns": list(column_transform_info.get("final_keep_dimensions", [])),
            "exclude_patterns": [],
            "required_passthrough_columns": list(required_passthrough_cols),
            "final_materialized_columns": list(curated_cols),
        }
        unmatched_keep_patterns = []
        unmatched_keep_exclude_patterns = []
        if not curated_cols:
            log.error("No columns selected by STEP 1.2 keep_dimensions configuration.")
            return 1
        if missing_required_passthrough_cols:
            log.error(
                "STEP 1.2 required_passthrough_columns missing from dataset after transformations: %s",
                missing_required_passthrough_cols,
            )
            return 1
        column_transform_info["required_passthrough_columns"] = list(required_passthrough_cols)
        column_transform_info["final_materialized_columns"] = list(curated_cols)
        out = out[[c for c in curated_cols if c in out.columns]].copy()
    else:
        curated_cols, materialized_cols_info = resolve_materialized_feature_space_columns(
            available_columns=list(out.columns),
            feature_space_cfg=feature_space_cfg,
            fallback_patterns=requested_keep_patterns,
        )
        curated_cols, missing_required_passthrough_cols = _merge_materialized_with_required_columns(
            materialized_columns=curated_cols,
            required_columns=required_passthrough_cols,
            available_columns=list(out.columns),
        )
        unmatched_keep_patterns = list(materialized_cols_info.get("unmatched_include_patterns", []))
        unmatched_keep_exclude_patterns = list(materialized_cols_info.get("unmatched_exclude_patterns", []))
        materialized_cols_info = dict(materialized_cols_info)
        materialized_cols_info["required_passthrough_columns"] = list(required_passthrough_cols)
        materialized_cols_info["final_materialized_columns"] = list(curated_cols)
        if unmatched_keep_patterns:
            log.warning(
                "Configured materialized-column include patterns without matches: %s",
                unmatched_keep_patterns,
            )
        if unmatched_keep_exclude_patterns:
            log.warning(
                "Configured materialized-column exclude patterns without matches: %s",
                unmatched_keep_exclude_patterns,
            )
        if missing_required_passthrough_cols:
            log.error(
                "STEP 1.2 required_passthrough_columns missing from dataset after transformations: %s",
                missing_required_passthrough_cols,
            )
            return 1
        if not curated_cols:
            log.error("No columns selected by STEP 1.2 materialized feature-space configuration.")
            return 1
        out = out[curated_cols].copy()
    (
        derived_catalog_post_curation_presence,
        derived_catalog_post_curation_unmatched,
    ) = _catalog_presence_against_columns(
        catalog_entries=derived_columns_catalog,
        available_columns=list(out.columns),
        transform_options=transform_options,
    )

    best_tt_prefix = None
    dropped_tt_cols: list[str] = []
    if transform_options["keep_only_best_tt_prefix"]:
        # Keep only the highest-priority tt prefix that is present after curation.
        # Consider both individual breakdown columns and per-prefix global-rate summaries.
        available_tt_prefixes: set[str] = {
            p for p, cols in tt_cols_by_prefix.items()
            if any(c in out.columns for c in cols)
        }
        for _prefix, _rate_col in rate_col_by_prefix.items():
            if _rate_col in out.columns:
                vals = pd.to_numeric(out[_rate_col], errors="coerce")
                if vals.notna().any():
                    available_tt_prefixes.add(_prefix)
        best_tt_prefix = _select_best_tt_prefix(
            available_tt_prefixes, priority=preferred_prefixes_t
        )
        out, dropped_tt_cols = _drop_non_best_tt_columns(
            out,
            best_prefix=best_tt_prefix,
            tt_cols_by_prefix=tt_cols_by_prefix,
            rate_col_by_prefix=rate_col_by_prefix,
        )
        if dropped_tt_cols:
            log.info(
                "Kept tt prefix '%s'; dropped %d tt-rate columns from other prefixes: %s%s",
                best_tt_prefix,
                len(dropped_tt_cols),
                dropped_tt_cols[:8],
                " ..." if len(dropped_tt_cols) > 8 else "",
            )

    # Persist the curated transformed table before the expensive plot phase so
    # downstream steps can consume the rebuilt feature space even when matrix
    # plotting is slow for very wide vector-only experiments.
    out_csv = FILES_DIR / "transformed_feature_space.csv"
    out.to_csv(out_csv, index=False)
    log.info(
        "Wrote transformed feature space (pre-plot persist): %s (%d rows, %d columns)",
        out_csv,
        len(out),
        len(out.columns),
    )

    parameter_matrix_cols, unmatched_matrix_patterns, parameter_matrix_source = _resolve_parameter_matrix_columns(
        out,
        cfg_12=cfg_12,
        cfg_14=cfg_14,
        parameter_space_path=DEFAULT_STEP11_PARAMETER_SPACE,
    )
    if unmatched_matrix_patterns:
        log.warning(
            "Configured parameter_matrix_columns patterns without matches: %s",
            unmatched_matrix_patterns,
        )
    feature_matrix_cols, unmatched_feature_matrix_patterns, feature_matrix_source = _resolve_feature_matrix_columns(
        out,
        cfg_12=cfg_12,
        config=config,
        feature_space_cfg=feature_space_cfg,
        parameter_cols=parameter_matrix_cols,
    )
    (
        feature_matrix_cols_plot,
        feature_matrix_rate_hist_cols,
        feature_matrix_eff_cols,
        feature_matrix_rate_hist_placeholder_added,
        feature_matrix_eff_placeholder_added,
    ) = _resolve_feature_matrix_plot_columns(
        feature_matrix_cols,
        include_rate_histogram=include_rate_histogram_in_feature_matrix,
        include_efficiency_vectors=include_efficiency_vectors_in_feature_matrix,
        suppressed_patterns=feature_space_plot_suppressed_patterns,
    )
    if unmatched_feature_matrix_patterns:
        log.warning(
            "Configured feature_matrix_columns entries without matches: %s",
            unmatched_feature_matrix_patterns,
        )

    _plot_parameter_scatter_matrix(
        out,
        parameter_cols=parameter_matrix_cols,
        sample_max_rows=sample_max_rows,
        random_seed=plot_seed,
    )
    feature_matrix_plot_status = "matrix"
    feature_matrix_grouped_fallback: dict[str, object] | None = None
    grouped_feature_multicase: dict[str, object] | None = None
    plotted_scalar_cols = [
        c
        for c in feature_matrix_cols_plot
        if c not in (RATE_HIST_PLACEHOLDER_COL, EFF_PLACEHOLDER_COL) and c in out.columns
    ]
    if len(feature_matrix_cols_plot) < 2 or len(plotted_scalar_cols) < 2:
        feature_matrix_grouped_fallback = _make_grouped_feature_space_summary_plot(
            out,
            selected_feature_cols=feature_matrix_cols,
        )
        grouped_feature_multicase = _make_grouped_feature_space_multicase_plot(
            out,
            selected_feature_cols=feature_matrix_cols,
            n_cases=int(cfg_12.get("grouped_feature_multicase_n_rows", 12) or 12),
            random_seed=int(cfg_12.get("grouped_feature_multicase_random_seed", plot_seed) or plot_seed),
        )
        feature_matrix_plot_status = "grouped_feature_fallback"
    else:
        _plot_feature_scatter_matrix(
            out,
            feature_cols=feature_matrix_cols_plot,
            sample_max_rows=sample_max_rows,
            random_seed=plot_seed,
            rate_hist_suppressed_count=(0 if include_rate_histogram_in_feature_matrix else len(feature_matrix_rate_hist_cols)),
            eff_suppressed_count=(0 if include_efficiency_vectors_in_feature_matrix else len(feature_matrix_eff_cols)),
            max_side=feature_scatter_matrix_max_side,
        )

    out.to_csv(out_csv, index=False)
    log.info("Wrote transformed feature space: %s (%d rows, %d columns)", out_csv, len(out), len(out.columns))

    summary = {
        "input_csv": str(input_path),
        "output_csv": str(out_csv),
        "n_rows": int(len(out)),
        "n_columns": int(len(out.columns)),
        "min_simulated_efficiency": float(min_eff_sim),
        "preferred_prefix_order": list(preferred_prefixes_t),
        "feature_space_config_path": str(feature_space_config_path),
        "feature_space_config_loaded": bool(feature_space_cfg),
        "feature_space_transform_options": {
            "derive_canonical_global_rate": bool(transform_options["derive_canonical_global_rate"]),
            "derive_empirical_efficiencies": bool(transform_options["derive_empirical_efficiencies"]),
            "derive_physics_helpers": bool(transform_options["derive_physics_helpers"]),
            "derive_post_tt_plane_aggregates": bool(transform_options.get("derive_post_tt_plane_aggregates", False)),
            "column_transformations": bool(transform_options.get("column_transformations", False)),
            "keep_only_best_tt_prefix": bool(transform_options["keep_only_best_tt_prefix"]),
            "tt_prefix_priority": list(preferred_prefixes_t),
        },
        "column_transformations": column_transform_info,
        "post_tt_plane_aggregates_config": dict(post_tt_aggregate_cfg),
        "post_tt_plane_aggregates": post_tt_plane_aggregates_info,
        "derived_columns_catalog": [dict(item) for item in derived_columns_catalog],
        "derived_columns_catalog_pre_curation_presence": derived_catalog_pre_curation_presence,
        "derived_columns_catalog_pre_curation_unmatched": derived_catalog_pre_curation_unmatched,
        "derived_columns_catalog_post_curation_presence": derived_catalog_post_curation_presence,
        "derived_columns_catalog_post_curation_unmatched": derived_catalog_post_curation_unmatched,
        "empirical_efficiency_selected_prefix": empirical_selected_prefix,
        "empirical_efficiency_used_prefixes": empirical_used_prefixes,
        "global_rate_prefix_columns": rate_col_by_prefix,
        "standard_task_rate_columns_forced": added_standard_rate_cols,
        "tt_rate_columns_by_prefix": tt_cols_by_prefix,
        "canonical_global_rate_source_counts": canonical_source_counts,
        "best_tt_prefix_selected": best_tt_prefix,
        "dropped_tt_columns_count": int(len(dropped_tt_cols)),
        "dropped_tt_columns": dropped_tt_cols,
        "has_canonical_global_rate": bool("events_per_second_global_rate" in out.columns),
        "derived_helper_column_count_added": int(helper_count),
        "transform_keep_columns_requested": requested_keep_patterns,
        "transform_keep_columns_unmatched": unmatched_keep_patterns,
        "required_passthrough_columns": required_passthrough_cols,
        "required_passthrough_columns_missing": missing_required_passthrough_cols,
        "materialized_columns_source": materialized_cols_info.get("source"),
        "materialized_columns_include_patterns": materialized_cols_info.get("include_patterns"),
        "materialized_columns_exclude_patterns": materialized_cols_info.get("exclude_patterns"),
        "materialized_columns_required_passthrough": materialized_cols_info.get("required_passthrough_columns"),
        "materialized_columns_final": materialized_cols_info.get("final_materialized_columns"),
        "materialized_columns_unmatched_exclude_patterns": unmatched_keep_exclude_patterns,
        "parameter_matrix_columns_used": parameter_matrix_cols,
        "parameter_matrix_columns_unmatched": unmatched_matrix_patterns,
        "parameter_matrix_columns_source": parameter_matrix_source,
        "feature_matrix_columns_used": feature_matrix_cols,
        "feature_matrix_columns_plotted": feature_matrix_cols_plot,
        "feature_matrix_columns_unmatched": unmatched_feature_matrix_patterns,
        "feature_matrix_columns_source": feature_matrix_source,
        "feature_space_lower_triangle_suppressed_patterns": feature_space_plot_suppressed_patterns,
        "feature_matrix_plot_include_rate_histogram": bool(include_rate_histogram_in_feature_matrix),
        "feature_matrix_plot_include_efficiency_vectors": bool(include_efficiency_vectors_in_feature_matrix),
        "feature_scatter_matrix_max_side": int(feature_scatter_matrix_max_side),
        "feature_matrix_rate_histogram_columns_total": int(len(feature_matrix_rate_hist_cols)),
        "feature_matrix_efficiency_vector_columns_total": int(len(feature_matrix_eff_cols)),
        "feature_matrix_rate_histogram_columns_suppressed": int(
            len(feature_matrix_rate_hist_cols) if feature_matrix_rate_hist_placeholder_added else 0
        ),
        "feature_matrix_efficiency_vector_columns_suppressed": int(
            len(feature_matrix_eff_cols) if feature_matrix_eff_placeholder_added else 0
        ),
        "feature_matrix_rate_histogram_placeholder_added": bool(feature_matrix_rate_hist_placeholder_added),
        "feature_matrix_efficiency_vector_placeholder_added": bool(feature_matrix_eff_placeholder_added),
        "feature_matrix_plot_status": feature_matrix_plot_status,
        "feature_matrix_grouped_fallback": feature_matrix_grouped_fallback,
        "grouped_feature_multicase": grouped_feature_multicase,
        "parameter_matrix_plot_sample_max_rows": int(sample_max_rows),
        "parameter_matrix_plot_random_seed": int(plot_seed),
        "efficiency_scalar_controls": efficiency_scalar_control_info,
        "task4_efficiency_scalar_controls": task4_efficiency_scalar_control_info,
        "curated_feature_columns": curated_cols,
        "curated_feature_count": int(len(curated_cols)),
    }
    summary_path = FILES_DIR / "transform_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    log.info("Wrote transform summary: %s", summary_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
