#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_SIMULATION/MINGO_DICTIONARY_CREATION_AND_TEST/STEPS/STEP_1_SETUP/STEP_1_4_ENSURE_CONTINUITY_DICTIONARY/ensure_continuity_dictionary.py
Purpose: STEP 1.4 - Ensure dictionary continuity with simple pairwise checks.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-11
Runtime: python3
Usage: python3 PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_SIMULATION/MINGO_DICTIONARY_CREATION_AND_TEST/STEPS/STEP_1_SETUP/STEP_1_4_ENSURE_CONTINUITY_DICTIONARY/ensure_continuity_dictionary.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

import argparse
import fnmatch
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
from scipy.spatial import ConvexHull, QhullError, cKDTree


# -- Paths ---------------------------------------------------------------------
STEP_DIR = Path(__file__).resolve().parent
if STEP_DIR.parents[1].name == "STEPS":
    PIPELINE_DIR = STEP_DIR.parents[2]
else:
    PIPELINE_DIR = STEP_DIR.parents[1]
STEP_ROOT = PIPELINE_DIR if (PIPELINE_DIR / "STEP_1_SETUP").exists() else PIPELINE_DIR / "STEPS"
DEFAULT_CONFIG = (
    STEP_ROOT / "STEP_1_SETUP" / "STEP_1_1_COLLECT_DATA" / "INPUTS" / "config_step_1.1_method.json"
)
DEFAULT_DICTIONARY = STEP_DIR.parent / "STEP_1_3_BUILD_DICTIONARY" / "OUTPUTS" / "FILES" / "dictionary.csv"
DEFAULT_DATASET = STEP_DIR.parent / "STEP_1_3_BUILD_DICTIONARY" / "OUTPUTS" / "FILES" / "dataset.csv"
DEFAULT_SELECTED_FEATURES = (
    STEP_DIR.parent / "STEP_1_3_BUILD_DICTIONARY" / "OUTPUTS" / "FILES" / "selected_feature_columns.json"
)
DEFAULT_PARAMETER_SPACE = (
    STEP_DIR.parent / "STEP_1_1_COLLECT_DATA" / "OUTPUTS" / "FILES" / "parameter_space_columns.json"
)
STEP12_TRANSFORM_DIR = STEP_DIR.parent / "STEP_1_2_TRANSFORM_FEATURE_SPACE"
STEP2_INFERENCE_DIR = PIPELINE_DIR / "STEPS" / "STEP_2_INFERENCE"

FILES_DIR = STEP_DIR / "OUTPUTS" / "FILES"
PLOTS_DIR = STEP_DIR / "OUTPUTS" / "PLOTS"
FILES_DIR.mkdir(parents=True, exist_ok=True)
PLOTS_DIR.mkdir(parents=True, exist_ok=True)

_FIGURE_COUNTER = 0
FIGURE_STEP_PREFIX = "1_4"

# Fixed internals to keep STEP 1.4 low-knob.
MIN_FEATURE_NON_NULL_FRACTION = 0.50
OUTLIER_SIGMA = 3.0
STATUS_WARN_REMOVAL_FRAC = 0.25
STATUS_FAIL_REMOVAL_FRAC = 0.50
SHOWCASE_NEIGHBORS = 80
HIST_RATE_COLUMN_RE = re.compile(r"^events_per_second_(?P<bin>\d+)_rate_hz$")
RATE_HIST_PLACEHOLDER_COL = "__RATE_HISTOGRAM_SUPPRESSED__"
RATE_HIST_PLACEHOLDER_LABEL = "events_per_second_<bin>_rate_hz [suppressed]"
EFF_PLACEHOLDER_COL = "__EFFICIENCY_VECTORS_SUPPRESSED__"
EFF_PLACEHOLDER_LABEL = "efficiency_vector_<axis>_bin_*_eff [suppressed]"
PARAM_TO_FEATURE_BALL_RADIUS_FRACTION = 0.25
PARAM_TO_FEATURE_RANDOM_SEED = 1234


def _feature_placeholder_label(col: str) -> str | None:
    if col == RATE_HIST_PLACEHOLDER_COL:
        return RATE_HIST_PLACEHOLDER_LABEL
    if col == EFF_PLACEHOLDER_COL:
        return EFF_PLACEHOLDER_LABEL
    return None


def _feature_placeholder_message(
    *,
    x_col: str,
    y_col: str,
    rate_hist_count: int,
    efficiency_vector_count: int,
) -> str:
    has_rate = x_col == RATE_HIST_PLACEHOLDER_COL or y_col == RATE_HIST_PLACEHOLDER_COL
    has_eff = x_col == EFF_PLACEHOLDER_COL or y_col == EFF_PLACEHOLDER_COL
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


logging.basicConfig(format="[%(levelname)s] STEP_1.4 - %(message)s", level=logging.INFO)
log = logging.getLogger("STEP_1.4")

if str(STEP12_TRANSFORM_DIR) not in sys.path:
    sys.path.insert(0, str(STEP12_TRANSFORM_DIR))
try:
    from transform_feature_space import (  # noqa: E402
        _resolve_feature_matrix_plot_columns as _step12_resolve_feature_matrix_plot_columns,
        _resolve_feature_space_plot_suppression_patterns as _step12_resolve_feature_space_plot_suppression_patterns,
    )
except Exception as exc:  # pragma: no cover - import failure is fatal
    raise RuntimeError(
        f"Could not import STEP 1.2 transform helpers from {STEP12_TRANSFORM_DIR}: {exc}"
    ) from exc

if str(STEP2_INFERENCE_DIR) not in sys.path:
    sys.path.insert(0, str(STEP2_INFERENCE_DIR))
try:
    from estimate_parameters import (  # noqa: E402
        _filter_efficiency_vector_payloads,
        _prepare_efficiency_vector_group_payloads,
        load_distance_definition,
    )
except Exception as exc:  # pragma: no cover - import failure is fatal
    raise RuntimeError(f"Could not import estimate_parameters from {STEP2_INFERENCE_DIR}: {exc}") from exc


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
        cfg = _merge_dicts(cfg, json.loads(plots_path.read_text(encoding="utf-8")))
        log.info("Loaded plot config: %s", plots_path)

    runtime_path = path.with_name("config_step_1.1_runtime.json")
    if runtime_path.exists():
        cfg = _merge_dicts(cfg, json.loads(runtime_path.read_text(encoding="utf-8")))
        log.info("Loaded runtime overrides: %s", runtime_path)

    return cfg


def _normalize_string_list(raw: object) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        txt = raw.strip()
        return [txt] if txt else []
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
        txt = raw.strip().lower()
        if txt in {"1", "true", "yes", "on"}:
            return True
        if txt in {"0", "false", "no", "off"}:
            return False
    return bool(default)


def _load_selected_features(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    cols = payload.get("selected_feature_columns", []) if isinstance(payload, dict) else []
    return [c for c in cols if isinstance(c, str) and c.strip()]


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
            out.append(text)
            seen.add(text)
        if out:
            break
    return out


def _resolve_feature_columns(df: pd.DataFrame, cfg_14: dict, selected_features_path: Path) -> list[str]:
    raw = cfg_14.get("feature_columns", "auto")
    patterns: list[str]

    if isinstance(raw, str) and raw.strip().lower() in {"auto", "selected", "selected_json"}:
        patterns = _load_selected_features(selected_features_path)
    else:
        patterns = _normalize_string_list(raw)

    if not patterns:
        patterns = [
            "eff_empirical_1",
            "eff_empirical_2",
            "eff_empirical_3",
            "eff_empirical_4",
            "events_per_second_global_rate",
            "events_per_second_*_rate_hz",
        ]

    available = list(df.columns)
    resolved: list[str] = []
    seen: set[str] = set()
    for pat in patterns:
        if any(ch in pat for ch in ("*", "?", "[")):
            matches = [c for c in available if fnmatch.fnmatchcase(c, pat)]
        else:
            matches = [pat] if pat in df.columns else []
        for col in matches:
            if col not in seen:
                resolved.append(col)
                seen.add(col)
    return resolved


def _resolve_parameter_columns(
    df: pd.DataFrame,
    cfg_14: dict,
    *,
    parameter_space_path: Path,
) -> tuple[list[str], str]:
    raw = cfg_14.get("parameter_columns", "auto")

    requested: list[str]
    source = "step_1_4.parameter_columns"
    if isinstance(raw, str) and raw.strip().lower() == "auto":
        requested = _load_parameter_space_columns(parameter_space_path)
        if requested:
            source = f"artifact:{parameter_space_path.name}"
        else:
            raise ValueError(
                "STEP 1.4 parameter-space artifact is missing or empty: "
                f"{parameter_space_path}"
            )
    else:
        requested = _normalize_string_list(raw)
        source = "step_1_4.parameter_columns"

    resolved = [c for c in requested if c in df.columns]
    return resolved, source


def _robust_scale_matrix(x: np.ndarray) -> np.ndarray:
    med = np.nanmedian(x, axis=0)
    mad = np.nanmedian(np.abs(x - med), axis=0)
    scale = np.where(mad > 1e-12, 1.4826 * mad, np.nanstd(x, axis=0))
    scale = np.where(scale > 1e-12, scale, 1.0)
    return (x - med) / scale


def _robust_positive_z(v: np.ndarray) -> np.ndarray:
    arr = np.asarray(v, dtype=float)
    med = float(np.nanmedian(arr))
    mad = float(np.nanmedian(np.abs(arr - med)))
    scale = 1.4826 * mad if mad > 1e-12 else float(np.nanstd(arr))
    if not np.isfinite(scale) or scale <= 1e-12:
        scale = 1.0
    z = (arr - med) / scale
    return np.clip(z, 0.0, None)








def _is_rate_histogram_feature(col: str) -> bool:
    return HIST_RATE_COLUMN_RE.match(str(col)) is not None


def _resolve_feature_plot_columns(
    feature_cols: list[str],
    *,
    include_rate_histogram: bool,
    suppressed_patterns: Sequence[str] | None = None,
) -> tuple[list[str], list[str], list[str], bool, bool]:
    return _step12_resolve_feature_matrix_plot_columns(
        feature_cols,
        include_rate_histogram=include_rate_histogram,
        include_efficiency_vectors=True,
        suppressed_patterns=suppressed_patterns,
    )


def _matrix_cell_size(n_dim: int) -> float:
    if n_dim <= 10:
        return 1.35
    if n_dim <= 20:
        return 0.95
    if n_dim <= 36:
        return 0.64
    return 0.46


def _prepare_numeric_features(
    dictionary: pd.DataFrame,
    feature_cols: list[str],
    *,
    param_cols: list[str],
    min_feature_non_null_fraction: float = MIN_FEATURE_NON_NULL_FRACTION,
) -> tuple[pd.DataFrame, np.ndarray, np.ndarray, np.ndarray, list[str], dict[str, object]]:
    """Extract raw numeric feature and parameter matrices from dictionary.

    Returns un-normalised features; normalization is applied separately
    after distance-mode tuning.
    """
    feat_num = (
        dictionary[feature_cols]
        .apply(pd.to_numeric, errors="coerce")
        .replace([np.inf, -np.inf], np.nan)
    )
    non_null_frac = feat_num.notna().mean(axis=0)
    threshold = max(float(min_feature_non_null_fraction), 0.0)
    kept_feature_cols = [c for c in feature_cols if float(non_null_frac.get(c, 0.0)) >= threshold]

    if not kept_feature_cols:
        raise RuntimeError(
            f"No continuity feature columns remain after min_non_null_fraction={threshold:.2f}."
        )

    feat_num = (
        dictionary[kept_feature_cols]
        .apply(pd.to_numeric, errors="coerce")
        .replace([np.inf, -np.inf], np.nan)
    )

    par_num = (
        dictionary[param_cols]
        .apply(pd.to_numeric, errors="coerce")
        .replace([np.inf, -np.inf], np.nan)
    )
    feature_valid_mask = feat_num.notna().all(axis=1)
    param_valid_mask = par_num.notna().all(axis=1)
    valid_mask = feature_valid_mask & param_valid_mask
    valid_idx = np.flatnonzero(valid_mask.to_numpy())
    if len(valid_idx) < 3:
        raise RuntimeError(
            "Not enough valid dictionary rows for continuity check "
            f"(need >=3, got {len(valid_idx)}; "
            f"feature-complete={int(feature_valid_mask.sum())}, "
            f"parameter-complete={int(param_valid_mask.sum())})."
        )

    dict_valid = dictionary.iloc[valid_idx].copy().reset_index(drop=True)
    x_raw = feat_num.iloc[valid_idx].to_numpy(dtype=float)
    y = par_num.iloc[valid_idx].to_numpy(dtype=float)

    completeness_info = {
        "feature_columns_requested_count": int(len(feature_cols)),
        "feature_columns_used_count": int(len(kept_feature_cols)),
        "feature_columns_dropped_by_non_null_fraction": [
            str(col) for col in feature_cols if str(col) not in set(kept_feature_cols)
        ],
        "min_feature_non_null_fraction": float(threshold),
        "input_rows": int(len(dictionary)),
        "rows_with_complete_features": int(feature_valid_mask.sum()),
        "rows_with_complete_parameters": int(param_valid_mask.sum()),
        "rows_with_complete_feature_and_parameter_space": int(valid_mask.sum()),
        "rows_removed_incomplete_features": int((~feature_valid_mask).sum()),
        "rows_removed_incomplete_parameters": int((~param_valid_mask).sum()),
        "rows_removed_incomplete_feature_or_parameter_space": int((~valid_mask).sum()),
    }

    return dict_valid, x_raw, y, valid_idx, kept_feature_cols, completeness_info


def _pca_2d(x: np.ndarray) -> np.ndarray:
    arr = np.asarray(x, dtype=float)
    if arr.ndim != 2 or arr.shape[0] == 0:
        return np.zeros((0, 2), dtype=float)
    centered = arr - np.nanmean(arr, axis=0)
    centered = np.nan_to_num(centered, nan=0.0)

    if centered.shape[1] == 1:
        return np.column_stack([centered[:, 0], np.zeros(centered.shape[0], dtype=float)])

    _, _, vh = np.linalg.svd(centered, full_matrices=False)
    comp = vh[:2].T
    proj = centered @ comp
    if proj.shape[1] == 1:
        return np.column_stack([proj[:, 0], np.zeros(proj.shape[0], dtype=float)])
    return proj[:, :2]


def _compute_pairwise_continuity(
    *,
    dict_valid: pd.DataFrame,
    x_feat_zscore: np.ndarray,
    y_param: np.ndarray,
    param_cols: list[str],
    k_neighbors: int = 5,
) -> tuple[pd.DataFrame, np.ndarray, float, np.ndarray, np.ndarray]:
    """Continuity check using L1 (Manhattan) distance on robust-z-scored features."""
    n = x_feat_zscore.shape[0]
    k_use = min(k_neighbors, n - 1)
    k_query = k_use + 1  # cKDTree query includes self

    # Feature-space neighbors via cKDTree with L1 (Manhattan)
    tree_feat = cKDTree(x_feat_zscore)
    d_feat_all, i_feat_all = tree_feat.query(x_feat_zscore, k=k_query, p=1)
    if d_feat_all.ndim != 2:
        d_feat_all = d_feat_all[:, np.newaxis]
        i_feat_all = i_feat_all[:, np.newaxis]
    # Exclude self (column 0)
    d_feat = d_feat_all[:, 1:k_query].astype(float)
    i_feat = i_feat_all[:, 1:k_query].astype(int)

    nn_feat_dist = np.median(d_feat, axis=1)
    nn_feat_idx = i_feat[:, 0]

    # Parameter-space neighbors via cKDTree with L2
    y_norm = _robust_scale_matrix(y_param)
    tree_param = cKDTree(y_norm)
    d_param, i_param = tree_param.query(y_norm, k=k_query, p=2)
    if d_param.ndim != 2:
        d_param = d_param[:, np.newaxis]
        i_param = i_param[:, np.newaxis]

    nn_param_dist = np.median(d_param[:, 1:k_query].astype(float), axis=1)
    nn_param_idx = i_param[:, 1].astype(int)
    # L1 feature distance between parameter-space nearest neighbors
    feat_dist_from_param_nn = np.sum(
        np.abs(x_feat_zscore - x_feat_zscore[nn_param_idx]), axis=1,
    )

    flags = dict_valid.copy()
    flags["feature_distance_definition"] = "l1_robust_zscore"
    flags["nn_index_feature_space"] = nn_feat_idx
    flags["distance_feature_space"] = nn_feat_dist
    flags["nn_index_parameter_space"] = nn_param_idx
    flags["distance_parameter_space_l2_zscore"] = nn_param_dist
    flags["distance_feature_for_parameter_nn"] = feat_dist_from_param_nn

    # Compute median delta across k neighbors for each parameter column.
    nn_feat_indices = i_feat  # (n, k_use) — already excludes self
    delta_pct_for_score: list[np.ndarray] = []
    for j, pcol in enumerate(param_cols):
        center = y_param[:, j]
        # Median absolute delta across k feature-space neighbors.
        neigh_vals = y_param[nn_feat_indices, j]  # (n, k_neighbors)
        delta_abs = np.median(np.abs(neigh_vals - center[:, np.newaxis]), axis=1)
        pmin = float(np.nanmin(y_param[:, j]))
        pmax = float(np.nanmax(y_param[:, j]))
        prange = max(pmax - pmin, 1e-12)
        denom = np.where(np.abs(center) > 1e-12, np.abs(center), prange)
        delta_pct = delta_abs / denom * 100.0

        flags[f"delta_abs_{pcol}"] = delta_abs
        flags[f"delta_pct_{pcol}"] = delta_pct
        delta_pct_for_score.append(delta_pct)

    score = _robust_positive_z(nn_feat_dist)
    if delta_pct_for_score:
        stacked = np.column_stack(delta_pct_for_score)
        score_param = np.nanmean(np.column_stack([_robust_positive_z(stacked[:, j]) for j in range(stacked.shape[1])]), axis=1)
        score = score + score_param

    score_med = float(np.nanmedian(score))
    score_mad = float(np.nanmedian(np.abs(score - score_med)))
    score_scale = 1.4826 * score_mad if score_mad > 1e-12 else float(np.nanstd(score))
    if not np.isfinite(score_scale) or score_scale <= 1e-12:
        score_scale = 1.0
    score_threshold = score_med + OUTLIER_SIGMA * score_scale

    keep = score <= score_threshold
    flags["continuity_score"] = score
    flags["keep_by_continuity"] = keep.astype(bool)

    return flags, keep, float(score_threshold), nn_feat_idx, nn_param_idx


def _plot_spread_vs_feature_distance(flags: pd.DataFrame, *, param_cols: list[str]) -> None:
    if flags.empty or not param_cols:
        return

    x_all = pd.to_numeric(flags["distance_feature_space"], errors="coerce")
    keep_all = flags["keep_by_continuity"].astype(bool)

    n = len(param_cols)
    # Each panel is a 2×2 gridspec block: scatter + bottom hist + right hist.
    panel_w, panel_h = 5.0, 5.0
    hist_ratio = 0.22  # fraction of panel for marginal histograms
    fig = plt.figure(figsize=(panel_w, panel_h * n))
    import matplotlib.gridspec as gridspec

    outer = gridspec.GridSpec(n, 1, figure=fig, hspace=0.35)

    # Determine shared y-limits across all panels.
    y_max_global = 0.0
    panel_data: list[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, str] | None] = []
    for i, pcol in enumerate(param_cols):
        ycol = f"delta_abs_{pcol}"
        if ycol not in flags.columns:
            panel_data.append(None)
            continue
        y = pd.to_numeric(flags[ycol], errors="coerce")
        m = x_all.notna() & y.notna()
        if not bool(m.any()):
            panel_data.append(None)
            continue
        xv = x_all[m].to_numpy(dtype=float)
        yv = y[m].to_numpy(dtype=float)
        kv = keep_all[m].to_numpy(dtype=bool)
        y_max_global = max(y_max_global, float(np.nanmax(yv)))
        panel_data.append((xv, yv, kv, ~kv, pcol))

    n_bins = 40
    color_kept = "#4C78A8"
    color_flag = "#D7301F"

    for i, pdata in enumerate(panel_data):
        inner = gridspec.GridSpecFromSubplotSpec(
            2, 2,
            subplot_spec=outer[i],
            width_ratios=[1.0 - hist_ratio, hist_ratio],
            height_ratios=[1.0 - hist_ratio, hist_ratio],
            wspace=0.05,
            hspace=0.05,
        )
        ax_scatter = fig.add_subplot(inner[0, 0])
        ax_hist_x = fig.add_subplot(inner[1, 0], sharex=ax_scatter)
        ax_hist_y = fig.add_subplot(inner[0, 1], sharey=ax_scatter)
        ax_empty = fig.add_subplot(inner[1, 1])
        ax_empty.axis("off")

        if pdata is None:
            ax_scatter.axis("off")
            ax_hist_x.axis("off")
            ax_hist_y.axis("off")
            continue

        xv, yv, m_keep, m_flag, pcol = pdata
        ax_scatter.set_ylim(0, y_max_global * 1.05)

        # Scatter
        if bool(m_keep.any()):
            ax_scatter.scatter(xv[m_keep], yv[m_keep], s=10, alpha=0.30, color=color_kept, edgecolors="none", label="Kept")
        if bool(m_flag.any()):
            ax_scatter.scatter(xv[m_flag], yv[m_flag], s=14, alpha=0.50, color=color_flag, edgecolors="none", label="Flagged")
        ax_scatter.set_title(pcol, fontsize=9)
        ax_scatter.tick_params(labelsize=6)
        ax_scatter.grid(True, alpha=0.15)
        plt.setp(ax_scatter.get_xticklabels(), visible=False)
        ax_scatter.set_ylabel(f"Median |Δ param|", fontsize=8)
        if i == 0:
            ax_scatter.legend(loc="upper left", fontsize=6)

        # Bottom histogram (x-axis projection)
        x_bins = np.linspace(float(np.nanmin(xv)), float(np.nanmax(xv)), n_bins + 1)
        if bool(m_keep.any()):
            ax_hist_x.hist(xv[m_keep], bins=x_bins, color=color_kept, alpha=0.55, edgecolor="none")
        if bool(m_flag.any()):
            ax_hist_x.hist(xv[m_flag], bins=x_bins, color=color_flag, alpha=0.55, edgecolor="none")
        ax_hist_x.tick_params(labelsize=6)
        ax_hist_x.set_ylabel("Count", fontsize=7)
        if i == n - 1:
            ax_hist_x.set_xlabel("Feature dist. (median 5-NN)", fontsize=7)
        else:
            plt.setp(ax_hist_x.get_xticklabels(), visible=False)

        # Right histogram (y-axis projection, horizontal)
        y_bins = np.linspace(0, y_max_global * 1.05, n_bins + 1)
        if bool(m_keep.any()):
            ax_hist_y.hist(yv[m_keep], bins=y_bins, orientation="horizontal", color=color_kept, alpha=0.55, edgecolor="none")
        if bool(m_flag.any()):
            ax_hist_y.hist(yv[m_flag], bins=y_bins, orientation="horizontal", color=color_flag, alpha=0.55, edgecolor="none")
        ax_hist_y.tick_params(labelsize=6)
        plt.setp(ax_hist_y.get_yticklabels(), visible=False)
        ax_hist_y.set_xlabel("Count", fontsize=7)

    fig.suptitle("Feature distance vs parameter-space component deltas (median over 5 nearest neighbours)", fontsize=10, y=0.99)
    fig.subplots_adjust(top=0.92)
    _save_figure(fig, PLOTS_DIR / "continuity_spread_vs_feature_distance.png", dpi=150)
    plt.close(fig)


def _resolve_grouped_feature_blocks(
    df: pd.DataFrame,
    *,
    selected_feature_cols: list[str],
) -> tuple[dict[str, object], list[str], list[dict[str, object]], list[str]]:
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

    axes_to_plot = sorted(
        {
            str(payload.get("axis", "")).strip().lower()
            for payload in eff_payloads
            if str(payload.get("axis", "")).strip().lower() in {"x", "y", "theta"}
        },
        key=lambda axis: {"x": 0, "y": 1, "theta": 2}.get(axis, 99),
    )
    return dd, hist_cols, eff_payloads, axes_to_plot


def _parameter_order_coordinate(
    df: pd.DataFrame,
    *,
    param_cols: list[str],
) -> tuple[np.ndarray, str]:
    if not param_cols:
        return np.full(len(df), np.nan, dtype=float), "parameter_space"
    if len(param_cols) == 1:
        series = pd.to_numeric(df[param_cols[0]], errors="coerce")
        return series.to_numpy(dtype=float), str(param_cols[0])
    param_arr = df[param_cols].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    proj = _pca_2d(param_arr)
    return proj[:, 0].astype(float, copy=False), "parameter_space_pc1"


def _quantile_group_masks(values: np.ndarray) -> list[tuple[str, np.ndarray]]:
    finite = np.isfinite(values)
    if int(np.sum(finite)) < 3:
        return []
    q0, q1, q2, q3 = np.nanquantile(values[finite], [0.0, 1.0 / 3.0, 2.0 / 3.0, 1.0])
    intervals = [
        ("Low", q0, q1, False),
        ("Mid", q1, q2, False),
        ("High", q2, q3, True),
    ]
    out: list[tuple[str, np.ndarray]] = []
    for label, lo, hi, closed_right in intervals:
        if not np.isfinite(lo) or not np.isfinite(hi):
            continue
        if closed_right:
            mask = finite & (values >= lo) & (values <= hi)
        else:
            mask = finite & (values >= lo) & (values < hi)
        if bool(np.any(mask)):
            out.append((label, mask))
    if len(out) >= 2:
        return out
    return [("All", finite)]


def _plot_grouped_neighborhood_fallback(
    *,
    flags: pd.DataFrame,
    feature_cols: list[str],
    param_cols: list[str],
    out_path: Path | None = None,
) -> dict[str, object]:
    info: dict[str, object] = {
        "status": "skipped_no_grouped_blocks",
        "feature_plot_mode": "grouped_fallback",
        "parameter_order_axis": None,
        "rate_histogram_bins_used": 0,
        "efficiency_vector_groups_used": 0,
        "efficiency_vector_axes_used": [],
        "quantile_groups_used": [],
    }
    if not param_cols:
        info["status"] = "skipped_no_parameter_columns"
        return info

    used_cols = [c for c in param_cols if c in flags.columns]
    if not used_cols:
        info["status"] = "skipped_no_parameter_columns"
        return info
    work = flags.copy().reset_index(drop=True)
    param_valid = work[used_cols].apply(pd.to_numeric, errors="coerce").notna().all(axis=1)
    work = work.loc[param_valid].reset_index(drop=True)
    if len(work) < 3:
        info["status"] = "skipped_too_few_rows"
        return info

    dd, hist_cols, eff_payloads, axes_to_plot = _resolve_grouped_feature_blocks(
        work,
        selected_feature_cols=feature_cols,
    )
    info["rate_histogram_bins_used"] = int(len(hist_cols))
    info["efficiency_vector_groups_used"] = int(len(eff_payloads))
    info["efficiency_vector_axes_used"] = axes_to_plot
    info["distance_definition_available"] = bool(dd.get("available")) if isinstance(dd, dict) else False
    if not hist_cols and not eff_payloads:
        return info

    order_values, order_label = _parameter_order_coordinate(work, param_cols=used_cols)
    group_specs = _quantile_group_masks(order_values)
    if not group_specs:
        info["status"] = "skipped_too_few_rows"
        return info
    info["parameter_order_axis"] = order_label
    info["quantile_groups_used"] = [label for label, _ in group_specs]

    plot_path = out_path or (PLOTS_DIR / "neighborhood_correspondence_grouped_feature_fallback.png")
    n_panels = (1 if hist_cols else 0) + len(axes_to_plot)
    fig, axes = plt.subplots(
        n_panels,
        1,
        figsize=(11.6, max(3.0 * n_panels, 4.8)),
        squeeze=False,
    )
    axes_flat = axes[:, 0]
    panel_idx = 0
    group_colors = {"Low": "#1F77B4", "Mid": "#FF7F0E", "High": "#2CA02C", "All": "#1F77B4"}
    group_styles = {"Low": "-", "Mid": "--", "High": ":", "All": "-"}
    plane_colors = {1: "#1F77B4", 2: "#FF7F0E", 3: "#2CA02C", 4: "#D62728"}

    if hist_cols:
        ax = axes_flat[panel_idx]
        panel_idx += 1
        hist_bins = np.asarray(
            [int(HIST_RATE_COLUMN_RE.match(col).group("bin")) for col in hist_cols],
            dtype=float,
        )
        hist_frame = work[hist_cols].apply(pd.to_numeric, errors="coerce")
        for label, mask in group_specs:
            group_frame = hist_frame.loc[mask]
            if group_frame.empty:
                continue
            hist_med = group_frame.median(axis=0, skipna=True).to_numpy(dtype=float)
            ax.plot(
                hist_bins,
                hist_med,
                color=group_colors.get(label, "#1F77B4"),
                linestyle=group_styles.get(label, "-"),
                linewidth=1.8,
                label=f"{label} {order_label} tercile (n={int(mask.sum())})",
            )
        ax.set_xlabel("Rate-histogram bin index", fontsize=8)
        ax.set_ylabel("Rate [Hz]", fontsize=8)
        ax.set_title(f"Rate histogram evolution along {order_label}", fontsize=9)
        ax.grid(True, alpha=0.18)
        ax.legend(fontsize=7, loc="best", frameon=False)

    axis_payloads: dict[str, list[dict[str, object]]] = {"x": [], "y": [], "theta": []}
    for payload in eff_payloads:
        axis_name = str(payload.get("axis", "")).strip().lower()
        if axis_name in axis_payloads:
            axis_payloads[axis_name].append(payload)

    for axis_name in axes_to_plot:
        ax = axes_flat[panel_idx]
        panel_idx += 1
        for label, mask in group_specs:
            for payload in sorted(axis_payloads[axis_name], key=lambda item: int(item.get("plane", 0))):
                centers = np.asarray(payload.get("centers", []), dtype=float)
                if centers.size == 0:
                    continue
                eff_frame = pd.DataFrame(np.asarray(payload.get("dict_eff", []), dtype=float))
                group_frame = eff_frame.loc[mask]
                if group_frame.empty:
                    continue
                eff_med = group_frame.median(axis=0, skipna=True).to_numpy(dtype=float)
                valid = np.isfinite(centers) & np.isfinite(eff_med)
                if not np.any(valid):
                    continue
                plane = int(payload.get("plane", 0))
                ax.plot(
                    centers[valid],
                    eff_med[valid],
                    color=plane_colors.get(plane, "#4C78A8"),
                    linestyle=group_styles.get(label, "-"),
                    linewidth=1.3,
                    alpha=0.95,
                )
        axis_label = {"x": "Projected X [mm]", "y": "Projected Y [mm]", "theta": "Theta [deg]"}.get(axis_name, axis_name)
        ax.set_xlabel(axis_label, fontsize=8)
        ax.set_ylabel("Efficiency", fontsize=8)
        ax.set_ylim(0.0, 1.05)
        ax.set_title(
            f"Efficiency vectors vs {axis_name} along {order_label} "
            "(color=plane, linestyle=Low/Mid/High)",
            fontsize=9,
        )
        ax.grid(True, alpha=0.18)

    fig.suptitle("STEP 1.4 grouped feature continuity fallback", fontsize=12, y=0.995)
    fig.tight_layout(rect=[0, 0, 1, 0.985])
    _save_figure(fig, plot_path, dpi=150)
    plt.close(fig)
    info["status"] = "grouped_feature_fallback"
    info["n_panels"] = int(n_panels)
    return info


def _plot_grouped_ball_convex_fallback(
    *,
    flags: pd.DataFrame,
    feature_cols: list[str],
    param_cols: list[str],
    random_seed: int,
    radius_fraction: float,
    out_path: Path | None = None,
) -> dict[str, object]:
    info: dict[str, object] = {
        "status": "skipped_no_grouped_blocks",
        "feature_plot_mode": "grouped_fallback",
        "parameter_order_axis": None,
        "center_index": None,
        "selected_count": 0,
        "selected_fraction": 0.0,
        "rate_histogram_bins_used": 0,
        "efficiency_vector_groups_used": 0,
        "efficiency_vector_axes_used": [],
    }
    if radius_fraction <= 0.0:
        info["status"] = "skipped_non_positive_radius_fraction"
        return info
    if not param_cols:
        info["status"] = "skipped_no_parameter_columns"
        return info

    used_cols = [c for c in param_cols if c in flags.columns]
    if not used_cols:
        info["status"] = "skipped_no_parameter_columns"
        return info
    work = flags.copy().reset_index(drop=True)
    param_valid = work[used_cols].apply(pd.to_numeric, errors="coerce").notna().all(axis=1)
    work = work.loc[param_valid].reset_index(drop=True)
    if len(work) < 3:
        info["status"] = "skipped_too_few_rows"
        return info

    dd, hist_cols, eff_payloads, axes_to_plot = _resolve_grouped_feature_blocks(
        work,
        selected_feature_cols=feature_cols,
    )
    info["rate_histogram_bins_used"] = int(len(hist_cols))
    info["efficiency_vector_groups_used"] = int(len(eff_payloads))
    info["efficiency_vector_axes_used"] = axes_to_plot
    info["distance_definition_available"] = bool(dd.get("available")) if isinstance(dd, dict) else False
    if not hist_cols and not eff_payloads:
        return info

    order_values, order_label = _parameter_order_coordinate(work, param_cols=used_cols)
    finite = np.isfinite(order_values)
    if int(np.sum(finite)) < 3:
        info["status"] = "skipped_too_few_rows"
        return info
    info["parameter_order_axis"] = order_label

    rng = np.random.default_rng(int(random_seed))
    finite_idx = np.flatnonzero(finite)
    center_local_idx = int(rng.integers(0, len(finite_idx)))
    center_idx = int(finite_idx[center_local_idx])
    center_value = float(order_values[center_idx])
    order_range = float(np.nanmax(order_values[finite]) - np.nanmin(order_values[finite]))
    half_width = abs(center_value) * float(radius_fraction) if abs(center_value) > 1e-12 else order_range * float(radius_fraction)
    if not np.isfinite(half_width) or half_width <= 0.0:
        half_width = max(order_range * float(radius_fraction), 1e-9)
    selected_mask = finite & (np.abs(order_values - center_value) <= half_width)
    if not np.any(selected_mask):
        selected_mask[center_idx] = True

    info["center_index"] = int(center_idx)
    info["center_value"] = float(center_value)
    info["selected_count"] = int(np.sum(selected_mask))
    info["selected_fraction"] = float(np.sum(selected_mask) / max(1, len(work)))

    plot_path = out_path or (PLOTS_DIR / "param_to_feature_ball_convex_grouped_fallback.png")
    n_panels = (1 if hist_cols else 0) + len(axes_to_plot)
    fig, axes = plt.subplots(
        n_panels,
        1,
        figsize=(11.6, max(3.0 * n_panels, 4.8)),
        squeeze=False,
    )
    axes_flat = axes[:, 0]
    panel_idx = 0
    plane_colors = {1: "#1F77B4", 2: "#FF7F0E", 3: "#2CA02C", 4: "#D62728"}

    if hist_cols:
        ax = axes_flat[panel_idx]
        panel_idx += 1
        hist_bins = np.asarray(
            [int(HIST_RATE_COLUMN_RE.match(col).group("bin")) for col in hist_cols],
            dtype=float,
        )
        hist_frame = work[hist_cols].apply(pd.to_numeric, errors="coerce")
        full_med = hist_frame.median(axis=0, skipna=True).to_numpy(dtype=float)
        full_lo = hist_frame.quantile(0.25).to_numpy(dtype=float)
        full_hi = hist_frame.quantile(0.75).to_numpy(dtype=float)
        sel_frame = hist_frame.loc[selected_mask]
        sel_med = sel_frame.median(axis=0, skipna=True).to_numpy(dtype=float)
        ax.fill_between(hist_bins, full_lo, full_hi, color="#BDBDBD", alpha=0.28, label="Global IQR")
        ax.plot(hist_bins, full_med, color="#7F7F7F", linewidth=1.2, label="Global median")
        ax.plot(hist_bins, sel_med, color="#1F77B4", linewidth=1.9, label=f"Local window (n={int(np.sum(selected_mask))})")
        ax.set_xlabel("Rate-histogram bin index", fontsize=8)
        ax.set_ylabel("Rate [Hz]", fontsize=8)
        ax.set_title(f"Rate histogram near {order_label}={center_value:.3g}", fontsize=9)
        ax.grid(True, alpha=0.18)
        ax.legend(fontsize=7, loc="best", frameon=False)

    axis_payloads: dict[str, list[dict[str, object]]] = {"x": [], "y": [], "theta": []}
    for payload in eff_payloads:
        axis_name = str(payload.get("axis", "")).strip().lower()
        if axis_name in axis_payloads:
            axis_payloads[axis_name].append(payload)

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
            full_med = eff_frame.median(axis=0, skipna=True).to_numpy(dtype=float)
            sel_med = eff_frame.loc[selected_mask].median(axis=0, skipna=True).to_numpy(dtype=float)
            valid = np.isfinite(centers) & np.isfinite(full_med) & np.isfinite(sel_med)
            if not np.any(valid):
                continue
            plane = int(payload.get("plane", 0))
            color = plane_colors.get(plane, "#4C78A8")
            ax.plot(
                centers[valid],
                full_med[valid],
                color="#A9A9A9",
                linewidth=1.0,
                linestyle="--",
                alpha=0.9,
            )
            ax.plot(
                centers[valid],
                sel_med[valid],
                color=color,
                linewidth=1.5,
                label=f"Plane {plane}",
            )
        axis_label = {"x": "Projected X [mm]", "y": "Projected Y [mm]", "theta": "Theta [deg]"}.get(axis_name, axis_name)
        ax.set_xlabel(axis_label, fontsize=8)
        ax.set_ylabel("Efficiency", fontsize=8)
        ax.set_ylim(0.0, 1.05)
        ax.set_title(
            f"Efficiency vectors near {order_label}={center_value:.3g} "
            "(gray dashed = global median)",
            fontsize=9,
        )
        ax.grid(True, alpha=0.18)
        handles, labels = ax.get_legend_handles_labels()
        if handles:
            ax.legend(fontsize=7, loc="best", frameon=False, ncol=min(4, len(handles)))

    fig.suptitle("STEP 1.4 grouped local-window fallback", fontsize=12, y=0.995)
    fig.tight_layout(rect=[0, 0, 1, 0.985])
    _save_figure(fig, plot_path, dpi=150)
    plt.close(fig)
    info["status"] = "grouped_feature_fallback"
    info["n_panels"] = int(n_panels)
    return info


def _plot_bidirectional_neighborhood_showcase(
    *,
    x_feat: np.ndarray,
    y_param: np.ndarray,
    flags: pd.DataFrame,
    feature_p_norm: int,
    feature_cols: list[str],
    param_cols: list[str],
    include_rate_histogram_features: bool,
    plot_background_max_rows: int,
    suppressed_patterns: Sequence[str] | None = None,
) -> dict[str, object]:
    include_rate_histogram = bool(include_rate_histogram_features)
    info: dict[str, object] = {
        "feature_plot_columns_used": [],
        "feature_plot_columns_count": 0,
        "feature_space_lower_triangle_suppressed_patterns": list(suppressed_patterns or []),
        "feature_plot_include_rate_histogram": bool(include_rate_histogram),
        "feature_plot_rate_histogram_columns_total": 0,
        "feature_plot_rate_histogram_columns_suppressed": 0,
        "feature_plot_rate_histogram_placeholder_added": False,
        "feature_plot_efficiency_vector_columns_total": 0,
        "feature_plot_efficiency_vector_columns_suppressed": 0,
        "feature_plot_efficiency_vector_placeholder_added": False,
        "feature_plot_status": "skipped",
    }
    if x_feat.shape[0] < 8:
        return info

    param_cols = [c for c in (param_cols or []) if c in flags.columns]
    feat_cols_all = [c for c in (feature_cols or []) if c in flags.columns]
    (
        feat_cols_plot,
        hist_cols,
        eff_cols,
        hist_placeholder_added,
        eff_placeholder_added,
    ) = _resolve_feature_plot_columns(
        feat_cols_all,
        include_rate_histogram=include_rate_histogram,
        suppressed_patterns=suppressed_patterns,
    )
    info["feature_plot_columns_used"] = feat_cols_plot
    info["feature_plot_columns_count"] = int(len(feat_cols_plot))
    info["feature_plot_include_rate_histogram"] = bool(include_rate_histogram)
    info["feature_plot_rate_histogram_columns_total"] = int(len(hist_cols))
    info["feature_plot_rate_histogram_columns_suppressed"] = int(len(hist_cols) if hist_placeholder_added else 0)
    info["feature_plot_rate_histogram_placeholder_added"] = bool(hist_placeholder_added)
    info["feature_plot_efficiency_vector_columns_total"] = int(len(eff_cols))
    info["feature_plot_efficiency_vector_columns_suppressed"] = int(
        len(eff_cols) if eff_placeholder_added else 0
    )
    info["feature_plot_efficiency_vector_placeholder_added"] = bool(eff_placeholder_added)

    if len(param_cols) < 2 or len(feat_cols_plot) < 2:
        fallback_info = _plot_grouped_neighborhood_fallback(
            flags=flags,
            feature_cols=feat_cols_all,
            param_cols=param_cols,
        )
        if str(fallback_info.get("status", "")).startswith("grouped_feature_fallback"):
            info.update(fallback_info)
            info["feature_plot_status"] = str(fallback_info.get("status"))
            return info
        log.warning("Skipping continuity neighborhood matrices: need >=2 parameter cols and >=2 feature cols.")
        info["feature_plot_status"] = str(fallback_info.get("status", "skipped_insufficient_dimensions"))
        return info

    used_cols = sorted(set(param_cols + feat_cols_all))
    work = flags[used_cols].apply(pd.to_numeric, errors="coerce").dropna().reset_index(drop=True)
    if len(work) < 8:
        log.warning("Skipping continuity neighborhood matrices: too few valid rows.")
        info["feature_plot_status"] = "skipped_too_few_rows"
        return info

    param_arr = work[param_cols].to_numpy(dtype=float)
    feat_arr = work[feat_cols_all].to_numpy(dtype=float)

    def _minmax_normalize(arr: np.ndarray) -> np.ndarray:
        lo = np.nanmin(arr, axis=0)
        hi = np.nanmax(arr, axis=0)
        span = hi - lo
        span = np.where(np.isfinite(span) & (span > 0.0), span, 1.0)
        return (arr - lo) / span

    def _pick_local_knn_neighborhood(arr_norm: np.ndarray, n_pick: int) -> np.ndarray:
        n_rows = int(arr_norm.shape[0])
        if n_rows <= n_pick:
            return np.arange(n_rows, dtype=int)
        # Use cKDTree to avoid O(n^2) full distance matrix allocation.
        k_anchor = max(2, min(n_pick - 1, n_rows - 1))
        tree = cKDTree(arr_norm)
        # k+1 because the query includes the point itself (distance 0).
        dists, _ = tree.query(arr_norm, k=k_anchor + 1, p=2)
        local_compactness = np.mean(dists[:, 1:k_anchor + 1], axis=1)
        anchor = int(np.argmin(local_compactness))
        # Retrieve the n_pick nearest points to the anchor (includes anchor).
        _, neighbor_indices = tree.query(arr_norm[anchor], k=n_pick, p=2)
        return np.asarray(neighbor_indices, dtype=int)

    def _build_subset_knn_edges(source_norm: np.ndarray, idx_subset: np.ndarray, k_graph: int = 2) -> list[tuple[int, int]]:
        n_subset = int(len(idx_subset))
        if n_subset < 2:
            return []
        local = source_norm[idx_subset]
        diffs = local[:, None, :] - local[None, :, :]
        dmat = np.sqrt(np.sum(diffs * diffs, axis=2))
        np.fill_diagonal(dmat, np.inf)
        k_use = max(1, min(int(k_graph), n_subset - 1))
        edges: set[tuple[int, int]] = set()
        for i in range(n_subset):
            nn = np.argsort(dmat[i], kind="mergesort")[:k_use]
            for j in nn:
                a, b = sorted((int(i), int(j)))
                edges.add((a, b))
        return sorted(edges)

    def _selected_topology_overlap(
        source_norm: np.ndarray,
        target_norm: np.ndarray,
        idx_subset: np.ndarray,
        k_eval: int,
    ) -> tuple[float, float]:
        n_rows = int(source_norm.shape[0])
        if n_rows < 3 or len(idx_subset) == 0:
            return np.nan, np.nan
        k_use = max(2, min(int(k_eval), n_rows - 1))
        overlaps: list[float] = []
        for ridx in idx_subset:
            i = int(ridx)
            src_d = np.sqrt(np.sum((source_norm - source_norm[i]) ** 2, axis=1))
            tgt_d = np.sqrt(np.sum((target_norm - target_norm[i]) ** 2, axis=1))
            src_d[i] = np.inf
            tgt_d[i] = np.inf
            src_nn = np.argpartition(src_d, kth=k_use - 1)[:k_use]
            tgt_nn = np.argpartition(tgt_d, kth=k_use - 1)[:k_use]
            overlaps.append(float(len(set(src_nn.tolist()).intersection(tgt_nn.tolist())) / k_use))
        arr = np.asarray(overlaps, dtype=float)
        if arr.size == 0:
            return np.nan, np.nan
        return float(np.percentile(arr, 10)), float(np.median(arr))

    def _selected_distance_correlation(
        source_norm: np.ndarray,
        target_norm: np.ndarray,
        idx_subset: np.ndarray,
    ) -> float:
        n_subset = int(len(idx_subset))
        if n_subset < 3:
            return np.nan
        src_local = source_norm[idx_subset]
        tgt_local = target_norm[idx_subset]
        src_d = np.sqrt(np.sum((src_local[:, None, :] - src_local[None, :, :]) ** 2, axis=2))
        tgt_d = np.sqrt(np.sum((tgt_local[:, None, :] - tgt_local[None, :, :]) ** 2, axis=2))
        tri = np.triu_indices(n_subset, k=1)
        src_v = src_d[tri]
        tgt_v = tgt_d[tri]
        if src_v.size < 2:
            return np.nan
        if np.nanstd(src_v) < 1e-12 or np.nanstd(tgt_v) < 1e-12:
            return np.nan
        corr = np.corrcoef(src_v, tgt_v)[0, 1]
        return float(corr) if np.isfinite(corr) else np.nan

    p_norm = _minmax_normalize(param_arr)
    f_norm = _minmax_normalize(feat_arr)
    n_pick = int(np.clip(12, 6, min(18, len(work))))
    idx_param_near = _pick_local_knn_neighborhood(p_norm, n_pick)
    idx_feat_near = _pick_local_knn_neighborhood(f_norm, n_pick)
    marker_colors = plt.cm.tab20(np.linspace(0.0, 1.0, n_pick))
    rng_plot = np.random.default_rng(1234)

    def _draw_lower_triangle(
        subfig,
        cols: list[str],
        idx_subset: np.ndarray,
        edges: list[tuple[int, int]],
        background_idx: np.ndarray,
        draw_edges: bool,
        title: str,
    ) -> None:
        n_dim = len(cols)
        if n_dim < 2:
            ax = subfig.subplots(1, 1)
            ax.axis("off")
            ax.text(0.5, 0.5, "Insufficient dimensions", ha="center", va="center")
            return
        # Reserve a small top band for the subfigure title to avoid overlap with axes.
        subfig.subplots_adjust(top=0.90)
        axes = subfig.subplots(n_dim - 1, n_dim - 1, squeeze=False)
        subfig.suptitle(title, fontsize=10, y=0.955)
        for row in range(n_dim - 1):
            y_idx = row + 1
            y_col = cols[y_idx]
            for col in range(n_dim - 1):
                ax = axes[row, col]
                if col >= y_idx:
                    ax.axis("off")
                    continue
                x_col = cols[col]
                x_label = _feature_placeholder_label(x_col)
                y_label = _feature_placeholder_label(y_col)
                x_is_placeholder = x_label is not None
                y_is_placeholder = y_label is not None
                if x_is_placeholder or y_is_placeholder:
                    ax.set_facecolor("#F5F5F5")
                    if (x_is_placeholder and y_is_placeholder) or (y_is_placeholder and col == 0):
                        ax.text(
                            0.5,
                            0.5,
                            _feature_placeholder_message(
                                x_col=x_col,
                                y_col=y_col,
                                rate_hist_count=len(hist_cols),
                                efficiency_vector_count=len(eff_cols),
                            ),
                            ha="center",
                            va="center",
                            fontsize=7,
                            transform=ax.transAxes,
                        )
                else:
                    x_all = work[x_col].to_numpy(dtype=float)
                    y_all = work[y_col].to_numpy(dtype=float)
                    ax.scatter(
                        x_all[background_idx],
                        y_all[background_idx],
                        s=4.5,
                        color="#C7C7C7",
                        alpha=0.20,
                        edgecolors="none",
                        zorder=1,
                        rasterized=True,
                    )
                    if draw_edges and edges:
                        for edge_a, edge_b in edges:
                            idx_a = int(idx_subset[edge_a])
                            idx_b = int(idx_subset[edge_b])
                            ax.plot(
                                [x_all[idx_a], x_all[idx_b]],
                                [y_all[idx_a], y_all[idx_b]],
                                color="#7F7F7F",
                                alpha=0.26,
                                linewidth=0.55,
                                zorder=2,
                            )
                    sel_x = x_all[idx_subset]
                    sel_y = y_all[idx_subset]
                    ax.scatter(
                        sel_x,
                        sel_y,
                        s=24,
                        c=marker_colors[: len(idx_subset)],
                        edgecolors="black",
                        linewidths=0.32,
                        zorder=3,
                    )
                if row == n_dim - 2:
                    ax.set_xlabel(x_label or x_col, fontsize=7)
                else:
                    ax.set_xticklabels([])
                if col == 0:
                    ax.set_ylabel(y_label or y_col, fontsize=7)
                else:
                    ax.set_yticklabels([])
                ax.tick_params(labelsize=6, length=2)
                ax.grid(True, alpha=0.18, linewidth=0.4, zorder=0)

    def _direction_summary(
        source_norm: np.ndarray,
        target_norm: np.ndarray,
        idx_subset: np.ndarray,
    ) -> str:
        k_eval = max(2, min(8, len(work) - 1))
        overlap_p10, overlap_med = _selected_topology_overlap(source_norm, target_norm, idx_subset, k_eval)
        dist_corr = _selected_distance_correlation(source_norm, target_norm, idx_subset)
        return (
            f"selected_k={len(idx_subset)}, "
            f"overlap_p10={overlap_p10:.3f}, "
            f"overlap_median={overlap_med:.3f}, "
            f"distance_corr={dist_corr:.3f}"
        )

    def _plot_direction(
        idx_subset: np.ndarray,
        source_cols: list[str],
        target_cols: list[str],
        source_name: str,
        target_name: str,
        source_norm: np.ndarray,
        target_norm: np.ndarray,
        out_name_suffix: str,
    ) -> None:
        summary = _direction_summary(source_norm, target_norm, idx_subset)
        edges = _build_subset_knn_edges(source_norm, idx_subset, k_graph=2)
        n_rows = int(len(work))
        if plot_background_max_rows > 0 and n_rows > plot_background_max_rows:
            keep = rng_plot.choice(np.arange(n_rows), size=int(plot_background_max_rows), replace=False)
            background_idx = np.unique(np.concatenate([keep, idx_subset]))
        else:
            background_idx = np.arange(n_rows, dtype=int)
        draw_edges = max(len(source_cols), len(target_cols)) <= 16
        source_grid = max(1, len(source_cols) - 1)
        target_grid = max(1, len(target_cols) - 1)
        source_cell = _matrix_cell_size(len(source_cols))
        target_cell = _matrix_cell_size(len(target_cols))
        left_w = max(4.8, source_grid * source_cell + 1.2)
        right_w = max(4.8, target_grid * target_cell + 1.2)
        fig_h = max(5.8, max(source_grid * source_cell, target_grid * target_cell) + 2.6)
        fig = plt.figure(figsize=(left_w + right_w + 1.2, fig_h))
        try:
            subfigs = fig.subfigures(1, 2, wspace=0.03, width_ratios=[left_w, right_w])
        except TypeError:
            subfigs = fig.subfigures(1, 2, wspace=0.03)
        _draw_lower_triangle(
            subfigs[0],
            source_cols,
            idx_subset,
            edges,
            background_idx,
            draw_edges,
            f"Selected neighborhood in {source_name} space",
        )
        _draw_lower_triangle(
            subfigs[1],
            target_cols,
            idx_subset,
            edges,
            background_idx,
            draw_edges,
            f"Mapped neighborhood in {target_name} space",
        )
        handles = [
            plt.Line2D(
                [0],
                [0],
                marker="o",
                linestyle="",
                markerfacecolor=marker_colors[i],
                markeredgecolor="black",
                markeredgewidth=0.35,
                markersize=5.5,
                label=str(i + 1),
            )
            for i in range(len(idx_subset))
        ]
        fig.legend(
            handles=handles,
            loc="lower center",
            ncol=min(12, len(idx_subset)),
            fontsize=7,
            frameon=False,
            title="Selected points (same colors in source and mapped matrices)",
            title_fontsize=8,
            bbox_to_anchor=(0.5, 0.01),
        )
        fig.suptitle(
            f"Neighborhood continuity matrix: {source_name} -> {target_name}",
            fontsize=12,
            y=0.995,
        )
        fig.text(
            0.5,
            0.972,
            summary,
            ha="center",
            va="top",
            fontsize=9,
        )
        _save_figure(
            fig,
            PLOTS_DIR / f"neighborhood_correspondence_{out_name_suffix}.png",
            dpi=120,
        )
        plt.close(fig)

    _plot_direction(
        idx_param_near,
        param_cols,
        feat_cols_plot,
        source_name="Parameter",
        target_name="Feature",
        source_norm=p_norm,
        target_norm=f_norm,
        out_name_suffix="param_to_feature_matrix",
    )
    _plot_direction(
        idx_feat_near,
        feat_cols_plot,
        param_cols,
        source_name="Feature",
        target_name="Parameter",
        source_norm=f_norm,
        target_norm=p_norm,
        out_name_suffix="feature_to_param_matrix",
    )
    info["feature_plot_status"] = "ok"
    return info


def _plot_param_to_feature_ball_convex_showcase(
    *,
    flags: pd.DataFrame,
    feature_cols: list[str],
    param_cols: list[str],
    include_rate_histogram_features: bool,
    random_seed: int,
    radius_fraction: float,
    suppressed_patterns: Sequence[str] | None = None,
) -> dict[str, object]:
    include_rate_histogram = bool(include_rate_histogram_features)
    info: dict[str, object] = {
        "status": "skipped",
        "random_seed": int(random_seed),
        "radius_fraction_per_dimension": float(radius_fraction),
        "center_index": None,
        "selected_count": 0,
        "selected_fraction": 0.0,
        "feature_plot_columns_used": [],
        "feature_plot_columns_count": 0,
        "feature_space_lower_triangle_suppressed_patterns": list(suppressed_patterns or []),
        "feature_plot_include_rate_histogram": bool(include_rate_histogram),
        "feature_plot_rate_histogram_columns_total": 0,
        "feature_plot_rate_histogram_columns_suppressed": 0,
        "feature_plot_rate_histogram_placeholder_added": False,
        "feature_plot_efficiency_vector_columns_total": 0,
        "feature_plot_efficiency_vector_columns_suppressed": 0,
        "feature_plot_efficiency_vector_placeholder_added": False,
    }

    if radius_fraction <= 0.0:
        info["status"] = "skipped_non_positive_radius_fraction"
        return info

    param_cols = [c for c in (param_cols or []) if c in flags.columns]
    feat_cols_all = [c for c in (feature_cols or []) if c in flags.columns]
    (
        feat_cols_plot,
        hist_cols,
        eff_cols,
        hist_placeholder_added,
        eff_placeholder_added,
    ) = _resolve_feature_plot_columns(
        feat_cols_all,
        include_rate_histogram=include_rate_histogram,
        suppressed_patterns=suppressed_patterns,
    )
    info["feature_plot_columns_used"] = feat_cols_plot
    info["feature_plot_columns_count"] = int(len(feat_cols_plot))
    info["feature_plot_include_rate_histogram"] = bool(include_rate_histogram)
    info["feature_plot_rate_histogram_columns_total"] = int(len(hist_cols))
    info["feature_plot_rate_histogram_columns_suppressed"] = int(len(hist_cols) if hist_placeholder_added else 0)
    info["feature_plot_rate_histogram_placeholder_added"] = bool(hist_placeholder_added)
    info["feature_plot_efficiency_vector_columns_total"] = int(len(eff_cols))
    info["feature_plot_efficiency_vector_columns_suppressed"] = int(
        len(eff_cols) if eff_placeholder_added else 0
    )
    info["feature_plot_efficiency_vector_placeholder_added"] = bool(eff_placeholder_added)

    n_plotted = len(feat_cols_plot)
    n_total = len(feat_cols_all)
    suppressed_parts: list[str] = []
    if hist_placeholder_added and hist_cols:
        suppressed_parts.append(f"{len(hist_cols)} bulk-rate columns -> 1 placeholder")
    if eff_placeholder_added and eff_cols:
        suppressed_parts.append(f"{len(eff_cols)} efficiency-vector columns -> 1 placeholder")
    log.info(
        "Ball-convex plot — parameter cols: %d | feature cols to plot: %d / %d total%s",
        len(param_cols),
        n_plotted,
        n_total,
        f" ({'; '.join(suppressed_parts)})" if suppressed_parts else "",
    )

    if len(param_cols) < 2 or len(feat_cols_plot) < 2:
        fallback_info = _plot_grouped_ball_convex_fallback(
            flags=flags,
            feature_cols=feat_cols_all,
            param_cols=param_cols,
            random_seed=random_seed,
            radius_fraction=radius_fraction,
        )
        if str(fallback_info.get("status", "")).startswith("grouped_feature_fallback"):
            info.update(fallback_info)
            return info
        log.warning(
            "Skipping random-ball param->feature matrix: need >=2 parameter cols and >=2 feature cols."
        )
        info["status"] = str(fallback_info.get("status", "skipped_insufficient_dimensions"))
        return info

    used_cols = sorted(set(param_cols + feat_cols_all))
    work = flags[used_cols].apply(pd.to_numeric, errors="coerce").dropna().reset_index(drop=True)
    if len(work) < 3:
        log.warning("Skipping random-ball param->feature matrix: too few valid rows.")
        info["status"] = "skipped_too_few_rows"
        return info

    param_arr = work[param_cols].to_numpy(dtype=float)

    rng = np.random.default_rng(int(random_seed))
    center_idx = int(rng.integers(0, len(work)))
    center_raw = param_arr[center_idx]
    # Per-dimension relative window: keep rows where each parameter is
    # within center * (1 ± radius_fraction).  For parameters near zero,
    # fall back to the column range scaled by radius_fraction.
    abs_center = np.abs(center_raw)
    col_range = np.ptp(param_arr, axis=0)
    half_width = np.where(
        abs_center > 1e-12,
        abs_center * radius_fraction,
        col_range * radius_fraction,
    )
    inside = np.all(
        np.abs(param_arr - center_raw[np.newaxis, :]) <= half_width[np.newaxis, :],
        axis=1,
    )
    idx_subset = np.flatnonzero(inside).astype(int)
    if len(idx_subset) == 0:
        idx_subset = np.asarray([center_idx], dtype=int)

    info["center_index"] = int(center_idx)
    info["ball_radius_fraction_per_dimension"] = float(radius_fraction)
    info["selected_count"] = int(len(idx_subset))
    info["selected_fraction"] = float(len(idx_subset) / max(1, len(work)))

    column_arrays: dict[str, np.ndarray] = {
        c: work[c].to_numpy(dtype=float)
        for c in used_cols
    }

    def _convex_ring_2d(x: np.ndarray, y: np.ndarray) -> np.ndarray | None:
        pts = np.column_stack([x, y])
        pts = pts[np.all(np.isfinite(pts), axis=1)]
        if pts.shape[0] < 3:
            return None
        pts = np.unique(pts, axis=0)
        if pts.shape[0] < 3:
            return None
        try:
            hull = ConvexHull(pts)
        except (QhullError, ValueError):
            return None
        hull_pts = pts[hull.vertices]
        if hull_pts.shape[0] < 3:
            return None
        return np.vstack([hull_pts, hull_pts[0]])

    def _draw_lower_triangle_with_ball_hull(
        subfig,
        cols: list[str],
        title: str,
    ) -> None:
        n_dim = len(cols)
        if n_dim < 2:
            ax = subfig.subplots(1, 1)
            ax.axis("off")
            ax.text(0.5, 0.5, "Insufficient dimensions", ha="center", va="center")
            return
        subfig.subplots_adjust(top=0.90)
        axes = subfig.subplots(n_dim - 1, n_dim - 1, squeeze=False)
        subfig.suptitle(title, fontsize=10, y=0.955)
        for row in range(n_dim - 1):
            y_idx = row + 1
            y_col = cols[y_idx]
            for col in range(n_dim - 1):
                ax = axes[row, col]
                if col >= y_idx:
                    ax.axis("off")
                    continue
                x_col = cols[col]
                x_label = _feature_placeholder_label(x_col)
                y_label = _feature_placeholder_label(y_col)
                x_is_placeholder = x_label is not None
                y_is_placeholder = y_label is not None
                if x_is_placeholder or y_is_placeholder:
                    ax.set_facecolor("#F5F5F5")
                    if (x_is_placeholder and y_is_placeholder) or (y_is_placeholder and col == 0):
                        ax.text(
                            0.5,
                            0.5,
                            _feature_placeholder_message(
                                x_col=x_col,
                                y_col=y_col,
                                rate_hist_count=len(hist_cols),
                                efficiency_vector_count=len(eff_cols),
                            ),
                            ha="center",
                            va="center",
                            fontsize=7,
                            transform=ax.transAxes,
                        )
                else:
                    x_all = column_arrays[x_col]
                    y_all = column_arrays[y_col]
                    x_sel = x_all[idx_subset]
                    y_sel = y_all[idx_subset]
                    ax.scatter(
                        x_all,
                        y_all,
                        s=5,
                        color="#C7C7C7",
                        alpha=0.22,
                        edgecolors="none",
                        zorder=1,
                    )
                    hull_ring = _convex_ring_2d(x_sel, y_sel)
                    if hull_ring is not None:
                        ax.fill(
                            hull_ring[:, 0],
                            hull_ring[:, 1],
                            color="#FDBB84",
                            alpha=0.22,
                            zorder=2,
                        )
                        ax.plot(
                            hull_ring[:, 0],
                            hull_ring[:, 1],
                            color="#E6550D",
                            linewidth=1.0,
                            alpha=0.9,
                            zorder=3,
                        )
                    ax.scatter(
                        x_sel,
                        y_sel,
                        s=24,
                        color="#2C7FB8",
                        alpha=0.85,
                        edgecolors="black",
                        linewidths=0.25,
                        zorder=4,
                    )
                    ax.scatter(
                        [x_all[center_idx]],
                        [y_all[center_idx]],
                        s=120,
                        marker="*",
                        color="#D62728",
                        edgecolors="black",
                        linewidths=0.4,
                        zorder=5,
                    )
                if row == n_dim - 2:
                    ax.set_xlabel(x_label or x_col, fontsize=7)
                else:
                    ax.set_xticklabels([])
                if col == 0:
                    ax.set_ylabel(y_label or y_col, fontsize=7)
                else:
                    ax.set_yticklabels([])
                ax.tick_params(labelsize=6, length=2)
                ax.grid(True, alpha=0.18, linewidth=0.4, zorder=0)

    source_grid = max(1, len(param_cols) - 1)
    target_grid = max(1, len(feat_cols_plot) - 1)
    source_cell = _matrix_cell_size(len(param_cols))
    target_cell = _matrix_cell_size(len(feat_cols_plot))
    left_w = max(4.8, source_grid * source_cell + 1.2)
    right_w = max(4.8, target_grid * target_cell + 1.2)
    fig_h = max(5.8, max(source_grid * source_cell, target_grid * target_cell) + 2.6)
    fig = plt.figure(figsize=(left_w + right_w + 1.2, fig_h))
    try:
        subfigs = fig.subfigures(1, 2, wspace=0.03, width_ratios=[left_w, right_w])
    except TypeError:
        subfigs = fig.subfigures(1, 2, wspace=0.03)

    _draw_lower_triangle_with_ball_hull(
        subfigs[0],
        param_cols,
        "Ball in parameter space + convex hull",
    )
    _draw_lower_triangle_with_ball_hull(
        subfigs[1],
        feat_cols_plot,
        "Image in feature space + convex hull",
    )

    legend_handles = [
        plt.Line2D(
            [0],
            [0],
            marker="o",
            linestyle="",
            markerfacecolor="#C7C7C7",
            markeredgecolor="none",
            markersize=5,
            alpha=0.8,
            label="All dictionary rows",
        ),
        plt.Line2D(
            [0],
            [0],
            marker="o",
            linestyle="",
            markerfacecolor="#2C7FB8",
            markeredgecolor="black",
            markeredgewidth=0.25,
            markersize=5.5,
            label=f"Rows within \u00b1{radius_fraction:.0%} per dim",
        ),
        plt.Line2D(
            [0],
            [0],
            marker="*",
            linestyle="",
            markerfacecolor="#D62728",
            markeredgecolor="black",
            markeredgewidth=0.35,
            markersize=9,
            label="Center x0",
        ),
        plt.Line2D(
            [0],
            [0],
            color="#E6550D",
            linewidth=1.2,
            label="Convex hull",
        ),
    ]
    fig.legend(
        handles=legend_handles,
        loc="lower center",
        ncol=4,
        fontsize=7,
        frameon=False,
        bbox_to_anchor=(0.5, 0.01),
    )
    fig.suptitle(
        "Neighborhood correspondence (ball + convex hull): Parameter -> Feature",
        fontsize=12,
        y=0.995,
    )
    fig.text(
        0.5,
        0.972,
        (
            f"seed={int(random_seed)}, center_index={center_idx}, "
            f"\u00b1{radius_fraction:.0%} per dimension, selected={len(idx_subset)}/{len(work)}"
        ),
        ha="center",
        va="top",
        fontsize=9,
    )
    _save_figure(
        fig,
        PLOTS_DIR / "neighborhood_correspondence_param_to_feature_ball_convex_matrix.png",
        dpi=150,
        bbox_inches="tight",
    )
    plt.close(fig)
    info["status"] = "ok"
    return info


def main() -> int:
    parser = argparse.ArgumentParser(description="STEP 1.4: Ensure continuity of dictionary with simple pairwise checks.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--dictionary-csv", default=None)
    parser.add_argument("--dataset-csv", default=None)
    args = parser.parse_args()

    config = _load_config(Path(args.config))
    _clear_plots_dir()

    cfg_12 = config.get("step_1_2", {}) if isinstance(config, dict) else {}
    cfg_14 = config.get("step_1_4", {}) if isinstance(config, dict) else {}
    include_rate_histogram_features = _as_bool(
        cfg_14.get(
            "feature_matrix_plot_include_rate_histogram",
            cfg_12.get("feature_matrix_plot_include_rate_histogram", True),
        ),
        default=True,
    )
    feature_space_plot_suppressed_patterns = _step12_resolve_feature_space_plot_suppression_patterns(
        config,
        step_cfg=cfg_14 if isinstance(cfg_14, dict) else {},
    )
    try:
        plot_background_max_rows = int(
            cfg_14.get("neighborhood_matrix_plot_sample_max_rows", 900)
        )
    except (TypeError, ValueError):
        plot_background_max_rows = 900
    plot_background_max_rows = max(0, plot_background_max_rows)
    ball_convex_enabled = _as_bool(
        cfg_14.get("param_to_feature_ball_convex_enabled", False),
        default=False,
    )
    raw_ball_seed = cfg_14.get("param_to_feature_random_ball_seed", PARAM_TO_FEATURE_RANDOM_SEED)
    try:
        random_ball_seed = int(raw_ball_seed)
    except (TypeError, ValueError):
        random_ball_seed = int(PARAM_TO_FEATURE_RANDOM_SEED)
        log.warning(
            "Invalid step_1_4.param_to_feature_random_ball_seed=%r; fallback to %d.",
            raw_ball_seed,
            random_ball_seed,
        )
    raw_ball_radius_fraction = cfg_14.get(
        "param_to_feature_ball_radius_fraction",
        PARAM_TO_FEATURE_BALL_RADIUS_FRACTION,
    )
    try:
        random_ball_radius_fraction = float(raw_ball_radius_fraction)
    except (TypeError, ValueError):
        random_ball_radius_fraction = float(PARAM_TO_FEATURE_BALL_RADIUS_FRACTION)
        log.warning(
            "Invalid step_1_4.param_to_feature_ball_radius_fraction=%r; fallback to %.3f.",
            raw_ball_radius_fraction,
            random_ball_radius_fraction,
        )
    if not np.isfinite(random_ball_radius_fraction) or random_ball_radius_fraction <= 0.0:
        random_ball_radius_fraction = float(PARAM_TO_FEATURE_BALL_RADIUS_FRACTION)
        log.warning(
            "Non-positive step_1_4.param_to_feature_ball_radius_fraction=%r; fallback to %.3f.",
            raw_ball_radius_fraction,
            random_ball_radius_fraction,
        )
    dict_cfg = cfg_14.get("dictionary_csv") if isinstance(cfg_14, dict) else None
    data_cfg = cfg_14.get("dataset_csv") if isinstance(cfg_14, dict) else None

    if args.dictionary_csv:
        dictionary_path = Path(args.dictionary_csv).expanduser()
    elif dict_cfg not in (None, "", "null", "None"):
        dictionary_path = Path(str(dict_cfg)).expanduser()
    else:
        dictionary_path = DEFAULT_DICTIONARY

    if args.dataset_csv:
        dataset_path = Path(args.dataset_csv).expanduser()
    elif data_cfg not in (None, "", "null", "None"):
        dataset_path = Path(str(data_cfg)).expanduser()
    else:
        dataset_path = DEFAULT_DATASET

    selected_features_path = DEFAULT_SELECTED_FEATURES

    if not dictionary_path.exists():
        log.error("Dictionary CSV not found: %s", dictionary_path)
        return 1
    if not dataset_path.exists():
        log.error("Dataset CSV not found: %s", dataset_path)
        return 1

    dictionary = pd.read_csv(dictionary_path, low_memory=False)
    dataset = pd.read_csv(dataset_path, low_memory=False)
    if dictionary.empty:
        log.error("Input dictionary is empty: %s", dictionary_path)
        return 1

    feature_cols_requested = _resolve_feature_columns(dictionary, cfg_14, selected_features_path)
    try:
        param_cols, param_cols_source = _resolve_parameter_columns(
            dictionary,
            cfg_14,
            parameter_space_path=DEFAULT_PARAMETER_SPACE,
        )
    except ValueError as exc:
        log.error("%s", exc)
        return 1
    if not feature_cols_requested:
        log.error("No feature columns resolved for STEP 1.4 continuity.")
        return 1
    if not param_cols:
        log.error("No parameter columns resolved for STEP 1.4 continuity.")
        return 1

    try:
        min_feature_non_null_fraction = float(
            cfg_14.get("min_feature_non_null_fraction", MIN_FEATURE_NON_NULL_FRACTION)
        )
    except (TypeError, ValueError):
        min_feature_non_null_fraction = float(MIN_FEATURE_NON_NULL_FRACTION)
    min_feature_non_null_fraction = max(min_feature_non_null_fraction, 0.0)

    try:
        (
            dict_valid,
            x_raw,
            y_param,
            valid_idx,
            feature_cols_used,
            feature_space_completeness,
        ) = _prepare_numeric_features(
            dictionary,
            feature_cols_requested,
            param_cols=param_cols,
            min_feature_non_null_fraction=min_feature_non_null_fraction,
        )
    except RuntimeError as exc:
        log.error("%s", exc)
        return 1
    log.info(
        "Prepared continuity arrays: valid_rows=%d, feature_dims=%d, param_dims=%d.",
        len(dict_valid),
        x_raw.shape[1],
        y_param.shape[1],
    )
    if int(feature_space_completeness.get("rows_removed_incomplete_feature_or_parameter_space", 0)) > 0:
        log.info(
            "Dropped %d row(s) before continuity because the requested feature or parameter space was incomplete.",
            int(feature_space_completeness.get("rows_removed_incomplete_feature_or_parameter_space", 0)),
        )

    # ── L1 robust z-score for continuity checking ─────────────────────
    x_feat = _robust_scale_matrix(x_raw)
    log.info("Feature-space distance for continuity: L1 (Manhattan) on robust z-scored features.")
    (
        _feat_cols_plot_preview,
        _hist_cols_preview,
        _eff_cols_preview,
        _hist_placeholder_preview,
        _eff_placeholder_preview,
    ) = _resolve_feature_plot_columns(
        feature_cols_used,
        include_rate_histogram=include_rate_histogram_features,
        suppressed_patterns=feature_space_plot_suppressed_patterns,
    )
    _suppressed_preview_parts: list[str] = []
    if _hist_placeholder_preview and _hist_cols_preview:
        _suppressed_preview_parts.append(f"bulk-rate: {len(_hist_cols_preview)} -> 1 placeholder")
    if _eff_placeholder_preview and _eff_cols_preview:
        _suppressed_preview_parts.append(f"efficiency vectors: {len(_eff_cols_preview)} -> 1 placeholder")
    log.info(
        "Feature columns for plots: %d / %d total%s",
        len(_feat_cols_plot_preview),
        len(feature_cols_used),
        f" ({'; '.join(_suppressed_preview_parts)})" if _suppressed_preview_parts else "",
    )

    flags, keep_mask, score_threshold, _nn_feat_idx, _nn_param_idx = _compute_pairwise_continuity(
        dict_valid=dict_valid,
        x_feat_zscore=x_feat,
        y_param=y_param,
        param_cols=param_cols,
    )
    log.info("Computed pairwise continuity flags for %d rows.", len(flags))

    apply_continuity_filter = _as_bool(cfg_14.get("apply_continuity_filter", True), default=True)
    dict_out = (
        dict_valid.loc[keep_mask].copy().reset_index(drop=True)
        if apply_continuity_filter
        else dict_valid.copy().reset_index(drop=True)
    )

    removed = int(len(dict_valid) - len(dict_out)) if apply_continuity_filter else 0
    removal_fraction = float(removed / max(1, len(dict_valid)))

    status = "PASS"
    messages: list[str] = []
    if apply_continuity_filter and removal_fraction > STATUS_FAIL_REMOVAL_FRAC:
        status = "FAIL"
        messages.append(
            f"continuity filtering removed {removal_fraction:.1%} (> {STATUS_FAIL_REMOVAL_FRAC:.0%} fail threshold)"
        )
    elif apply_continuity_filter and removal_fraction > STATUS_WARN_REMOVAL_FRAC:
        status = "WARN"
        messages.append(
            f"continuity filtering removed {removal_fraction:.1%} (> {STATUS_WARN_REMOVAL_FRAC:.0%} warn threshold)"
        )

    if len(dict_out) < 3:
        status = "FAIL"
        messages.append("continuity-filtered dictionary has fewer than 3 rows")

    dict_out_path = FILES_DIR / "dictionary.csv"
    data_out_path = FILES_DIR / "dataset.csv"
    features_out_path = FILES_DIR / "selected_feature_columns.json"
    flags_out_path = FILES_DIR / "continuity_flags.csv"
    summary_out_path = FILES_DIR / "build_summary.json"

    dict_out.to_csv(dict_out_path, index=False)
    dataset.to_csv(data_out_path, index=False)
    flags.to_csv(flags_out_path, index=False)

    if selected_features_path.exists():
        features_out_path.write_text(selected_features_path.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        features_out_path.write_text(json.dumps({"selected_feature_columns": feature_cols_used}, indent=2), encoding="utf-8")

    _plot_spread_vs_feature_distance(flags, param_cols=param_cols)
    log.info("Wrote continuity spread-vs-distance plot.")
    neighborhood_plot_info = _plot_bidirectional_neighborhood_showcase(
        x_feat=x_feat,
        y_param=y_param,
        flags=flags,
        feature_p_norm=1,
        feature_cols=feature_cols_used,
        param_cols=param_cols,
        include_rate_histogram_features=include_rate_histogram_features,
        plot_background_max_rows=plot_background_max_rows,
        suppressed_patterns=feature_space_plot_suppressed_patterns,
    )
    log.info(
        "Neighborhood correspondence plot status: %s",
        neighborhood_plot_info.get("feature_plot_status", "unknown"),
    )
    ball_convex_plot_info = _plot_param_to_feature_ball_convex_showcase(
        flags=flags,
        feature_cols=feature_cols_used,
        param_cols=param_cols,
        include_rate_histogram_features=include_rate_histogram_features,
        random_seed=random_ball_seed,
        radius_fraction=random_ball_radius_fraction,
        suppressed_patterns=feature_space_plot_suppressed_patterns,
    )

    continuity_validation = {
        "enabled": True,
        "status": status,
        "messages": messages,
        "checks": {
            "feature_to_parameter_pairs": {
                "status": status,
                "distance_definition": "l1_robust_zscore",
                "score_threshold": float(score_threshold),
                "n_rows_valid": int(len(dict_valid)),
                "n_rows_kept": int(len(dict_out)),
            },
            "parameter_to_feature_pairs": {
                "status": "PASS",
                "distance_definition": "l1_robust_zscore",
                "median_feature_distance_for_parameter_nn": float(np.nanmedian(flags["distance_feature_for_parameter_nn"])),
            },
            "support_adequacy": {"status": "SKIPPED"},
            "local_continuity": {"status": "SKIPPED"},
        },
    }

    summary = {
        "input_dictionary_csv": str(dictionary_path),
        "input_dataset_csv": str(dataset_path),
        "output_dictionary_csv": str(dict_out_path),
        "output_dataset_csv": str(data_out_path),
        "selected_feature_columns_json": str(features_out_path),
        "continuity_flags_csv": str(flags_out_path),
        "n_rows_dictionary_input": int(len(dictionary)),
        "n_rows_dictionary_valid_for_continuity": int(len(dict_valid)),
        "n_rows_dictionary_output": int(len(dict_out)),
        "apply_continuity_filter": bool(apply_continuity_filter),
        "rows_removed_by_continuity": int(removed),
        "rows_removed_by_continuity_fraction": float(removal_fraction),
        "feature_space_completeness": feature_space_completeness,
        "feature_columns_requested": feature_cols_requested,
        "feature_columns_used": feature_cols_used,
        "min_feature_non_null_fraction": float(min_feature_non_null_fraction),
        "parameter_columns_used": param_cols,
        "parameter_columns_source": param_cols_source,
        "feature_matrix_plot_include_rate_histogram": bool(include_rate_histogram_features),
        "feature_space_lower_triangle_suppressed_patterns": feature_space_plot_suppressed_patterns,
        "neighborhood_matrix_plot_sample_max_rows": int(plot_background_max_rows),
        "neighborhood_plot": neighborhood_plot_info,
        "param_to_feature_ball_convex_enabled": bool(ball_convex_enabled),
        "neighborhood_plot_param_to_feature_ball_convex": ball_convex_plot_info,
        "param_to_feature_random_ball_seed": int(random_ball_seed),
        "param_to_feature_ball_radius_fraction": float(random_ball_radius_fraction),
        "feature_distance_definition": "l1_robust_zscore",
        "continuity_score_threshold": float(score_threshold),
        "continuity_validation": continuity_validation,
    }
    summary_out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    fail_on_error = _as_bool(cfg_14.get("fail_on_error", False), default=False)
    log.info("Wrote continuity-filtered dictionary: %s (%d rows)", dict_out_path, len(dict_out))
    log.info("Wrote dataset copy: %s (%d rows)", data_out_path, len(dataset))
    log.info("Wrote continuity summary: %s", summary_out_path)

    if fail_on_error and status == "FAIL":
        log.error("STEP 1.4 continuity status=FAIL and fail_on_error=true.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
