#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_COMPARISONS/MINGO_SIMULATION_VS_SIMULATION/MINGO_DICTIONARY_CREATION_AND_TEST/STEPS/STEP_2_INFERENCE/feature_columns_config.py
Purpose: Shared feature-column selection helpers.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-09
Runtime: python3
Usage: Imported by STEP_2.1 / STEP_3.3 / STEP_4.2 scripts.
Inputs: DataFrames and JSON selector path.
Outputs: Updated config_step_2.1_columns.json and resolved feature-column lists.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Mapping, Sequence

import pandas as pd

TT_RATE_COLUMN_RE = re.compile(r"^(?P<prefix>.+?)_tt_(?P<label>[^_]+)_rate_hz$")
RATE_HISTOGRAM_BIN_RE = re.compile(r"^events_per_second_(?P<bin>\d+)_rate_hz$")
AUTO_TT_PREFIX_PRIORITY = [
    "post",
    "fit_to_post",
    "fit",
    "list_to_fit",
    "list",
    "cal",
    "clean",
    "raw_to_clean",
    "raw",
    "corr",
    "task5_to_corr",
    "fit_to_corr",
    "definitive",
]


def _normalize_tt_label(label: object) -> str:
    text = str(label).strip()
    if not text:
        return ""
    try:
        value = float(text)
    except (TypeError, ValueError):
        return text
    if value.is_integer():
        return str(int(value))
    return text


def _is_multi_plane_tt_label(label: object) -> bool:
    norm = _normalize_tt_label(label)
    if len(norm) < 2:
        return False
    if not all(ch in {"1", "2", "3", "4"} for ch in norm):
        return False
    return len(set(norm)) == len(norm)


def _prefix_rank(prefix: str) -> int:
    try:
        return AUTO_TT_PREFIX_PRIORITY.index(prefix)
    except ValueError:
        return len(AUTO_TT_PREFIX_PRIORITY)


def _as_bool(value: object, default: bool = False) -> bool:
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


def parse_explicit_feature_columns(value: object) -> list[str]:
    """Parse explicit feature-column configuration into a clean list."""
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("[") and text.endswith("]"):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if str(x).strip()]
        if "," in text:
            return [x.strip() for x in text.split(",") if x.strip()]
        return [text]
    if isinstance(value, Sequence):
        out: list[str] = []
        for item in value:
            text = str(item).strip()
            if text:
                out.append(text)
        return out
    text = str(value).strip()
    return [text] if text else []


def discover_potential_feature_columns(df: pd.DataFrame) -> list[dict]:
    """
    Discover potential feature columns from dictionary headers.

    Current scope: all `*_rate_hz` columns, with TT metadata when available.
    """
    entries: list[dict] = []
    for col in df.columns:
        name = str(col).strip()
        if not name.endswith("_rate_hz"):
            continue
        tt_match = TT_RATE_COLUMN_RE.match(name)
        if tt_match is None:
            simple = name.removesuffix("_rate_hz")
            entries.append(
                {
                    "column_name": name,
                    "simple_name": simple,
                    "kind": "rate_hz",
                    "tt_prefix": None,
                    "tt_label": None,
                    "is_multi_plane_tt": False,
                }
            )
            continue
        prefix = str(tt_match.group("prefix")).strip()
        label_raw = tt_match.group("label")
        label = _normalize_tt_label(label_raw)
        entries.append(
            {
                "column_name": name,
                "simple_name": f"{prefix}:{label}",
                "kind": "tt_rate_hz",
                "tt_prefix": prefix,
                "tt_label": label,
                "is_multi_plane_tt": bool(_is_multi_plane_tt_label(label)),
            }
        )

    def _sort_key(entry: Mapping[str, object]) -> tuple:
        prefix = str(entry.get("tt_prefix") or "")
        label = str(entry.get("tt_label") or "")
        return (
            0 if entry.get("kind") == "tt_rate_hz" else 1,
            _prefix_rank(prefix),
            prefix,
            len(label),
            label,
            str(entry.get("column_name") or ""),
        )

    entries.sort(key=_sort_key)
    return entries


def _as_string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        return [text]
    if isinstance(value, Sequence):
        out: list[str] = []
        for item in value:
            text = str(item).strip()
            if text:
                out.append(text)
        return out
    text = str(value).strip()
    return [text] if text else []


def _parse_trigger_type_allowlist(value: object) -> list[str]:
    """Parse trigger-type allowlist into normalized unique labels."""
    raw = parse_explicit_feature_columns(value)
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        label = _normalize_tt_label(item)
        if not label:
            continue
        if not _is_multi_plane_tt_label(label):
            continue
        if label in seen:
            continue
        out.append(label)
        seen.add(label)
    return out


def _default_use_trigger_type(default_enabled_columns: Sequence[str]) -> bool:
    for col in default_enabled_columns:
        name = str(col).strip()
        match = TT_RATE_COLUMN_RE.match(name)
        if match is None:
            continue
        if _is_multi_plane_tt_label(match.group("label")):
            return True
    return False


def _default_use_rate_histogram(default_enabled_columns: Sequence[str]) -> bool:
    for col in default_enabled_columns:
        name = str(col).strip()
        if RATE_HISTOGRAM_BIN_RE.match(name):
            return True
    return False


def _load_catalog_if_exists(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _infer_prefix_from_default_enabled(default_enabled_columns: Sequence[str]) -> str:
    by_prefix: dict[str, int] = {}
    for col in default_enabled_columns:
        name = str(col).strip()
        match = TT_RATE_COLUMN_RE.match(name)
        if match is None:
            continue
        label = match.group("label")
        if not _is_multi_plane_tt_label(label):
            continue
        prefix = str(match.group("prefix")).strip()
        if not prefix:
            continue
        by_prefix[prefix] = by_prefix.get(prefix, 0) + 1
    if not by_prefix:
        return "last"
    return min(by_prefix.keys(), key=lambda p: (_prefix_rank(p), -by_prefix[p], p))


def _default_include_to_tt(default_enabled_columns: Sequence[str]) -> bool:
    for col in default_enabled_columns:
        name = str(col).strip()
        match = TT_RATE_COLUMN_RE.match(name)
        if match is None:
            continue
        if not _is_multi_plane_tt_label(match.group("label")):
            continue
        if "_to_" in str(match.group("prefix")):
            return True
    return False


def _default_include_generic_rate(default_enabled_columns: Sequence[str]) -> bool:
    for col in default_enabled_columns:
        name = str(col).strip()
        if not name.endswith("_rate_hz"):
            continue
        match = TT_RATE_COLUMN_RE.match(name)
        if match is None:
            return True
        if not _is_multi_plane_tt_label(match.group("label")):
            return True
    return False


def _normalize_prefix_selector(value: object) -> str:
    text = str(value).strip().lower()
    return text if text else "last"


def sync_feature_column_catalog(
    *,
    catalog_path: Path,
    dict_df: pd.DataFrame,
    default_enabled_columns: Sequence[str] = (),
) -> dict:
    """
    Create/update compact `config_step_2.1_columns.json` selector file.

    Compact format with category controls:
      - "prefix": "last" | explicit prefix name
      - "*_to_*_tt_*_rate_hz": bool
      - "categories.trigger_type.enabled": bool
      - "categories.trigger_type.trigger_types": list[str] (empty => all)
      - "categories.rate_histogram.enabled": bool

    Legacy alias kept for backwards compatibility:
      - "*_*_rate_hz" (mirrors categories.rate_histogram.enabled)
    """
    _ = dict_df  # intentionally unused; kept for API compatibility
    existing = _load_catalog_if_exists(catalog_path)

    raw_prefix = existing.get("prefix", existing.get("preffix", None))
    prefix = _normalize_prefix_selector(
        raw_prefix if raw_prefix is not None else _infer_prefix_from_default_enabled(default_enabled_columns)
    )
    include_to_tt = _as_bool(
        existing.get("*_to_*_tt_*_rate_hz", None),
        default=_default_include_to_tt(default_enabled_columns),
    )
    categories_existing = (
        existing.get("categories", {})
        if isinstance(existing.get("categories", {}), Mapping)
        else {}
    )
    trigger_cfg = (
        categories_existing.get("trigger_type", {})
        if isinstance(categories_existing.get("trigger_type", {}), Mapping)
        else {}
    )
    rate_hist_cfg = (
        categories_existing.get("rate_histogram", {})
        if isinstance(categories_existing.get("rate_histogram", {}), Mapping)
        else {}
    )
    use_trigger_type = _as_bool(
        trigger_cfg.get("enabled", None),
        default=_default_use_trigger_type(default_enabled_columns),
    )
    use_rate_histogram = _as_bool(
        rate_hist_cfg.get("enabled", existing.get("*_*_rate_hz", None)),
        default=_default_use_rate_histogram(default_enabled_columns)
        or _default_include_generic_rate(default_enabled_columns),
    )
    trigger_allowlist = _parse_trigger_type_allowlist(
        trigger_cfg.get("trigger_types", existing.get("trigger_type_labels", None))
    )

    out = {
        "prefix": prefix,
        "*_to_*_tt_*_rate_hz": bool(include_to_tt),
        "*_*_rate_hz": bool(use_rate_histogram),
        "categories": {
            "trigger_type": {
                "enabled": bool(use_trigger_type),
                "trigger_types": trigger_allowlist,
            },
            "rate_histogram": {
                "enabled": bool(use_rate_histogram),
            },
        },
    }

    new_text = json.dumps(out, indent=2, ensure_ascii=True) + "\n"
    old_text = ""
    if catalog_path.exists():
        try:
            old_text = catalog_path.read_text(encoding="utf-8")
        except OSError:
            old_text = ""
    if new_text != old_text:
        catalog_path.write_text(new_text, encoding="utf-8")
    return out


def _compile_regex_list(patterns: Sequence[str]) -> tuple[list[re.Pattern[str]], list[str]]:
    compiled: list[re.Pattern[str]] = []
    invalid: list[str] = []
    for raw in patterns:
        pat = str(raw).strip()
        if not pat:
            continue
        try:
            compiled.append(re.compile(pat))
        except re.error:
            invalid.append(pat)
    return compiled, invalid


def _resolve_feature_columns_from_legacy_catalog(
    *,
    catalog: Mapping[str, object],
    available_columns: Sequence[str],
) -> tuple[list[str], dict]:
    mode = str(catalog.get("selection_mode", "enabled")).strip().lower()
    if mode not in {"enabled", "patterns", "enabled_or_patterns", "all"}:
        mode = "enabled"

    target = str(catalog.get("pattern_target", "simple_name")).strip().lower()
    if target not in {"column_name", "simple_name", "both"}:
        target = "simple_name"

    include_patterns_raw = _as_string_list(catalog.get("include_patterns", []))
    exclude_patterns_raw = _as_string_list(catalog.get("exclude_patterns", []))
    include_patterns, invalid_include = _compile_regex_list(include_patterns_raw)
    exclude_patterns, invalid_exclude = _compile_regex_list(exclude_patterns_raw)

    available = {str(c) for c in available_columns}
    selected: list[str] = []
    seen: set[str] = set()
    n_available_entries = 0

    for item in catalog.get("columns", []):
        if not isinstance(item, Mapping):
            continue
        col_name = str(item.get("column_name", "")).strip()
        if not col_name or col_name not in available:
            continue
        n_available_entries += 1
        simple_name = str(item.get("simple_name", col_name))
        enabled = bool(item.get("enabled", False))

        if target == "column_name":
            targets = [col_name]
        elif target == "simple_name":
            targets = [simple_name]
        else:
            targets = [col_name, simple_name]

        if include_patterns:
            included = any(
                pattern.search(text)
                for pattern in include_patterns
                for text in targets
            )
        else:
            included = True
        excluded = any(
            pattern.search(text)
            for pattern in exclude_patterns
            for text in targets
        )
        by_patterns = included and not excluded

        if mode == "enabled":
            keep = enabled
        elif mode == "patterns":
            keep = by_patterns
        elif mode == "enabled_or_patterns":
            keep = enabled or by_patterns
        else:  # all
            keep = True

        if keep and col_name not in seen:
            selected.append(col_name)
            seen.add(col_name)

    info = {
        "selection_mode": mode,
        "pattern_target": target,
        "selected_count": int(len(selected)),
        "catalog_entries_available_in_data": int(n_available_entries),
        "invalid_include_patterns": invalid_include,
        "invalid_exclude_patterns": invalid_exclude,
    }
    return selected, info


def resolve_feature_columns_from_catalog(
    *,
    catalog: Mapping[str, object],
    available_columns: Sequence[str],
) -> tuple[list[str], dict]:
    """
    Resolve selected feature columns from `config_step_2.1_columns.json`.

    Supports both compact (3-key) and legacy catalog formats.
    """
    # Legacy support.
    if isinstance(catalog.get("columns"), list):
        return _resolve_feature_columns_from_legacy_catalog(
            catalog=catalog,
            available_columns=available_columns,
        )

    prefix_mode = _normalize_prefix_selector(catalog.get("prefix", catalog.get("preffix", "last")))
    include_to_tt = _as_bool(catalog.get("*_to_*_tt_*_rate_hz", False), default=False)

    categories = catalog.get("categories", {})
    if not isinstance(categories, Mapping):
        categories = {}
    trigger_cfg = categories.get("trigger_type", {})
    if not isinstance(trigger_cfg, Mapping):
        trigger_cfg = {}
    rate_hist_cfg = categories.get("rate_histogram", {})
    if not isinstance(rate_hist_cfg, Mapping):
        rate_hist_cfg = {}

    use_trigger_type = _as_bool(trigger_cfg.get("enabled", True), default=True)
    use_rate_histogram = _as_bool(
        rate_hist_cfg.get("enabled", catalog.get("*_*_rate_hz", False)),
        default=False,
    )
    trigger_allowlist = _parse_trigger_type_allowlist(
        trigger_cfg.get("trigger_types", catalog.get("trigger_type_labels", None))
    )
    trigger_allowset = set(trigger_allowlist)

    rate_columns = sorted({str(c).strip() for c in available_columns if str(c).strip().endswith("_rate_hz")})

    by_prefix: dict[str, list[str]] = {}
    rate_histogram_cols: list[str] = []
    other_generic_rate_cols: list[str] = []
    for name in rate_columns:
        match = TT_RATE_COLUMN_RE.match(name)
        if match is None:
            if (not include_to_tt) and ("_to_" in name):
                continue
            if RATE_HISTOGRAM_BIN_RE.match(name):
                rate_histogram_cols.append(name)
            else:
                # Keep legacy path available for non-histogram generic *_rate_hz columns.
                other_generic_rate_cols.append(name)
            continue
        prefix = str(match.group("prefix")).strip()
        label = match.group("label")
        if not _is_multi_plane_tt_label(label):
            # Generic selector intentionally targets non-TT rate columns
            # (e.g. metadata_rate_histogram bins). Non-canonical TT rates
            # stay out unless selected via the TT-prefix selector.
            continue
        norm_label = _normalize_tt_label(label)
        if trigger_allowset and norm_label not in trigger_allowset:
            continue
        if (not include_to_tt) and ("_to_" in prefix):
            continue
        by_prefix.setdefault(prefix, []).append(name)

    selected_tt: list[str] = []
    selected_prefix = None
    if by_prefix:
        if prefix_mode == "last":
            selected_prefix = min(
                by_prefix.keys(),
                key=lambda p: (_prefix_rank(p), -len(by_prefix[p]), p),
            )
            selected_tt = sorted(set(by_prefix.get(selected_prefix, [])))
        else:
            selected_prefix = prefix_mode
            selected_tt = sorted(set(by_prefix.get(prefix_mode, [])))

    selected: list[str] = []
    seen: set[str] = set()
    if use_trigger_type:
        for col in selected_tt:
            if col not in seen:
                selected.append(col)
                seen.add(col)

    if use_rate_histogram:
        for col in sorted(set(rate_histogram_cols)):
            if col not in seen:
                selected.append(col)
                seen.add(col)

    include_generic_rate_legacy = _as_bool(catalog.get("*_*_rate_hz", False), default=False)
    if include_generic_rate_legacy:
        for col in sorted(set(other_generic_rate_cols)):
            if col not in seen:
                selected.append(col)
                seen.add(col)

    info = {
        "selection_mode": "compact",
        "pattern_target": "compact",
        "selected_count": int(len(selected)),
        "catalog_entries_available_in_data": int(len(rate_columns)),
        "invalid_include_patterns": [],
        "invalid_exclude_patterns": [],
        "prefix_mode": prefix_mode,
        "selected_prefix": selected_prefix,
        "include_to_tt_rate_hz": bool(include_to_tt),
        "include_generic_rate_hz": bool(use_rate_histogram),
        "use_trigger_type": bool(use_trigger_type),
        "use_rate_histogram": bool(use_rate_histogram),
        "trigger_type_allowlist": trigger_allowlist,
        "n_rate_histogram_cols_available": int(len(rate_histogram_cols)),
        "n_other_generic_rate_cols_available": int(len(other_generic_rate_cols)),
        "include_generic_rate_hz_legacy": bool(include_generic_rate_legacy),
    }
    return selected, info
