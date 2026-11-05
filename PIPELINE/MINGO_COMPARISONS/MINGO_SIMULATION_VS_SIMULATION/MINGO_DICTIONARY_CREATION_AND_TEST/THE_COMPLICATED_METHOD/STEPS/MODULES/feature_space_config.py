#!/usr/bin/env python3
"""
Shared feature-space configuration helpers.
"""

from __future__ import annotations

import fnmatch
import json
from pathlib import Path
from typing import Mapping, Sequence


DEFAULT_FEATURE_SPACE_CONFIG_NAME = "config_step_1.2_feature_space.json"
LEGACY_FEATURE_SPACE_CONFIG_NAME = "config_feature_space.json"
DEFAULT_FEATURE_GROUP_CONFIG_NAME = "config_step_1.5_feature_groups.json"
LEGACY_FEATURE_GROUP_CONFIG_NAME = "config_feature_groups.json"


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


def _normalize_pattern_list(raw: object) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        text = raw.strip()
        return [text] if text else []
    if isinstance(raw, Sequence):
        out: list[str] = []
        for item in raw:
            text = str(item).strip()
            if text:
                out.append(text)
        return out
    text = str(raw).strip()
    return [text] if text else []


def _normalize_column_list(raw: object) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        text = raw.strip()
        return [text] if text else []
    if isinstance(raw, Mapping):
        out: list[str] = []
        for value in raw.values():
            out.extend(_normalize_column_list(value))
        return out
    if isinstance(raw, Sequence):
        out: list[str] = []
        for item in raw:
            text = str(item).strip()
            if text:
                out.append(text)
        return out
    text = str(raw).strip()
    return [text] if text else []


def _extract_ancillary_columns(feature_space_cfg: Mapping[str, object] | None) -> list[str]:
    """Return ancillary column patterns/names from feature-space config.

    Ancillary columns are not intended to be used as primary feature-space
    dimensions for estimation but may be kept as passthroughs for
    diagnostics/plots. This helper normalizes that config entry.
    """
    if not isinstance(feature_space_cfg, Mapping):
        return []
    raw = feature_space_cfg.get("ancillary_columns")
    # legacy key fallback
    if raw is None:
        raw = feature_space_cfg.get("ancillary", feature_space_cfg.get("passthrough_auxiliary"))
    return _normalize_column_list(raw)


def _extract_keep_dimensions(feature_space_cfg: Mapping[str, object] | None) -> list[str]:
    if not isinstance(feature_space_cfg, Mapping):
        return []
    raw = feature_space_cfg.get("column_transformations")
    if isinstance(raw, Mapping):
        keep_raw = raw.get("keep_dimensions", raw.get("keep_columns", raw.get("kept", raw.get("keep"))))
        keep = _normalize_column_list(keep_raw)
        if keep:
            return keep
    for key in ("keep_dimensions", "kept", "keep"):
        if key in feature_space_cfg:
            keep = _normalize_column_list(feature_space_cfg.get(key))
            if keep:
                return keep
    columns_cfg = feature_space_cfg.get("columns")
    if isinstance(columns_cfg, Mapping):
        keep_raw = columns_cfg.get("kept", columns_cfg.get("keep", columns_cfg.get("keep_dimensions")))
        keep = _normalize_column_list(keep_raw)
        if keep:
            return keep
    return []


def extract_keep_dimensions(feature_space_cfg: Mapping[str, object] | None) -> list[str]:
    return _extract_keep_dimensions(feature_space_cfg)


def _extract_new_dimension_names(feature_space_cfg: Mapping[str, object] | None) -> list[str]:
    if not isinstance(feature_space_cfg, Mapping):
        return []
    raw = feature_space_cfg.get("column_transformations")
    new_raw = None
    if isinstance(raw, Mapping):
        new_raw = raw.get("new_dimensions", raw.get("new_columns", raw.get("new")))
    if new_raw is None:
        for key in ("new_dimensions", "new", "new_columns"):
            if key in feature_space_cfg:
                new_raw = feature_space_cfg.get(key)
                break
    if new_raw is None:
        columns_cfg = feature_space_cfg.get("columns")
        if isinstance(columns_cfg, Mapping):
            new_raw = columns_cfg.get("new", columns_cfg.get("new_dimensions", columns_cfg.get("new_columns")))
    if not isinstance(new_raw, Mapping):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for key, value in new_raw.items():
        if isinstance(value, Mapping):
            for sub_key in value.keys():
                name = str(sub_key).strip()
                if not name or name in seen:
                    continue
                seen.add(name)
                out.append(name)
            continue
        name = str(key).strip()
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


def extract_feature_dimensions(feature_space_cfg: Mapping[str, object] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for col in _extract_keep_dimensions(feature_space_cfg) + _extract_new_dimension_names(feature_space_cfg):
        name = str(col).strip()
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


def _normalize_priority_list(raw: object, *, default: Sequence[str]) -> tuple[str, ...]:
    values = _normalize_pattern_list(raw)
    if not values:
        return tuple(str(v).strip() for v in default if str(v).strip())
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        out.append(text)
        seen.add(text)
    return tuple(out)


def resolve_feature_space_config_path(
    pipeline_dir: Path,
    *,
    config: Mapping[str, object] | None = None,
    step_cfg: Mapping[str, object] | None = None,
) -> Path:
    raw = None
    if isinstance(step_cfg, Mapping):
        raw = step_cfg.get("feature_space_config_json")
    if raw in (None, "", "null", "None") and isinstance(config, Mapping):
        raw = config.get("feature_space_config_json")
    if raw in (None, "", "null", "None"):
        primary = pipeline_dir / DEFAULT_FEATURE_SPACE_CONFIG_NAME
        if primary.exists():
            return primary
        legacy = pipeline_dir / LEGACY_FEATURE_SPACE_CONFIG_NAME
        if legacy.exists():
            return legacy
        return primary
    path = Path(str(raw)).expanduser()
    if path.is_absolute():
        return path
    return (pipeline_dir / path).resolve()


def resolve_feature_group_config_path(
    pipeline_dir: Path,
    *,
    config: Mapping[str, object] | None = None,
    step_cfg: Mapping[str, object] | None = None,
) -> Path:
    raw = None
    if isinstance(step_cfg, Mapping):
        raw = step_cfg.get("feature_group_config_json", step_cfg.get("feature_groups_config_json"))
    if raw in (None, "", "null", "None") and isinstance(config, Mapping):
        raw = config.get("feature_group_config_json", config.get("feature_groups_config_json"))
    if raw in (None, "", "null", "None"):
        primary = pipeline_dir / DEFAULT_FEATURE_GROUP_CONFIG_NAME
        if primary.exists():
            return primary
        legacy_groups = pipeline_dir / LEGACY_FEATURE_GROUP_CONFIG_NAME
        if legacy_groups.exists():
            return legacy_groups
        # Fallback to feature-space config for backward compatibility.
        primary_space = pipeline_dir / DEFAULT_FEATURE_SPACE_CONFIG_NAME
        if primary_space.exists():
            return primary_space
        legacy_space = pipeline_dir / LEGACY_FEATURE_SPACE_CONFIG_NAME
        if legacy_space.exists():
            return legacy_space
        return primary
    path = Path(str(raw)).expanduser()
    if path.is_absolute():
        return path
    return (pipeline_dir / path).resolve()


def load_feature_space_config(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _coerce_column_section(
    raw: object,
) -> tuple[bool, list[str], list[str], bool]:
    if raw is None:
        return False, [], [], False
    if isinstance(raw, Mapping):
        include_key_present = any(k in raw for k in ("include", "columns", "patterns"))
        include_raw = raw.get("include", raw.get("columns", raw.get("patterns", None)))
        exclude_raw = raw.get("exclude", raw.get("drop", raw.get("omit", [])))
        return (
            True,
            _normalize_pattern_list(include_raw),
            _normalize_pattern_list(exclude_raw),
            not include_key_present,
        )
    return True, _normalize_pattern_list(raw), [], False


def _resolve_glob_patterns(
    available_columns: Sequence[str],
    *,
    include_patterns: Sequence[str],
    exclude_patterns: Sequence[str],
    include_all_if_omitted: bool = False,
) -> tuple[list[str], list[str], list[str], list[str]]:
    available = [str(c) for c in available_columns if str(c).strip()]
    available_set = set(available)

    selected: list[str]
    unmatched_include: list[str] = []
    if include_all_if_omitted:
        selected = list(available)
    else:
        selected = []
        seen: set[str] = set()
        for pattern in include_patterns:
            if any(ch in str(pattern) for ch in ("*", "?", "[")):
                matches = [c for c in available if fnmatch.fnmatchcase(c, str(pattern))]
            else:
                matches = [str(pattern)] if str(pattern) in available_set else []
            if not matches:
                unmatched_include.append(str(pattern))
                continue
            for col in matches:
                if col in seen:
                    continue
                selected.append(col)
                seen.add(col)

    excluded_cols: list[str] = []
    unmatched_exclude: list[str] = []
    excluded_seen: set[str] = set()
    for pattern in exclude_patterns:
        if any(ch in str(pattern) for ch in ("*", "?", "[")):
            matches = [c for c in available if fnmatch.fnmatchcase(c, str(pattern))]
        else:
            matches = [str(pattern)] if str(pattern) in available_set else []
        if not matches:
            unmatched_exclude.append(str(pattern))
            continue
        for col in matches:
            if col in excluded_seen:
                continue
            excluded_cols.append(col)
            excluded_seen.add(col)

    excluded_set = set(excluded_cols)
    selected = [c for c in selected if c not in excluded_set]
    return selected, unmatched_include, unmatched_exclude, excluded_cols


def resolve_materialized_feature_space_columns(
    *,
    available_columns: Sequence[str],
    feature_space_cfg: Mapping[str, object] | None,
    fallback_patterns: Sequence[str],
) -> tuple[list[str], dict]:
    section_present = False
    include_patterns: list[str] = []
    exclude_patterns: list[str] = []
    include_all_if_omitted = False
    if isinstance(feature_space_cfg, Mapping):
        section_present, include_patterns, exclude_patterns, include_all_if_omitted = _coerce_column_section(
            feature_space_cfg.get("materialized_columns")
        )
    if section_present:
        resolved, unmatched_include, unmatched_exclude, excluded_cols = _resolve_glob_patterns(
            available_columns,
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns,
            include_all_if_omitted=include_all_if_omitted,
        )
        info = {
            "source": "feature_space_config.materialized_columns",
            "used_feature_space_config": True,
            "include_patterns": include_patterns,
            "exclude_patterns": exclude_patterns,
            "include_all_if_omitted": bool(include_all_if_omitted),
            "unmatched_include_patterns": unmatched_include,
            "unmatched_exclude_patterns": unmatched_exclude,
            "excluded_columns": excluded_cols,
        }
        return resolved, info

    keep_dimensions = _extract_keep_dimensions(feature_space_cfg)
    if keep_dimensions:
        available_set = {str(c) for c in available_columns if str(c).strip()}
        resolved = [c for c in keep_dimensions if c in available_set]
        unmatched = [c for c in keep_dimensions if c not in available_set]
        info = {
            "source": "feature_space_config.keep_dimensions",
            "used_feature_space_config": True,
            "include_patterns": list(keep_dimensions),
            "exclude_patterns": [],
            "include_all_if_omitted": False,
            "unmatched_include_patterns": unmatched,
            "unmatched_exclude_patterns": [],
            "excluded_columns": [],
        }
        return resolved, info

    resolved, unmatched_include, unmatched_exclude, excluded_cols = _resolve_glob_patterns(
        available_columns,
        include_patterns=list(fallback_patterns),
        exclude_patterns=[],
        include_all_if_omitted=False,
    )
    info = {
        "source": "step_1_2.transform_keep_columns",
        "used_feature_space_config": False,
        "include_patterns": list(fallback_patterns),
        "exclude_patterns": [],
        "include_all_if_omitted": False,
        "unmatched_include_patterns": unmatched_include,
        "unmatched_exclude_patterns": unmatched_exclude,
        "excluded_columns": excluded_cols,
    }
    return resolved, info


def resolve_selected_feature_space_columns(
    *,
    available_columns: Sequence[str],
    feature_space_cfg: Mapping[str, object] | None,
    fallback_columns: Sequence[str] | None = None,
) -> tuple[list[str], dict]:
    section_present = False
    include_patterns: list[str] = []
    exclude_patterns: list[str] = []
    include_all_if_omitted = False
    if isinstance(feature_space_cfg, Mapping):
        section_present, include_patterns, exclude_patterns, include_all_if_omitted = _coerce_column_section(
            feature_space_cfg.get("selected_feature_columns")
        )
    if section_present:
        resolved, unmatched_include, unmatched_exclude, excluded_cols = _resolve_glob_patterns(
            available_columns,
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns,
            include_all_if_omitted=include_all_if_omitted,
        )
        # remove ancillary columns if requested in config
        ancillary = _extract_ancillary_columns(feature_space_cfg)
        anc_excluded: list[str] = []
        if ancillary:
            for pat in ancillary:
                if any(ch in pat for ch in ("*", "?", "[")):
                    matches = [c for c in resolved if fnmatch.fnmatchcase(c, pat)]
                else:
                    matches = [c for c in resolved if c == pat]
                for m in matches:
                    if m not in anc_excluded:
                        anc_excluded.append(m)
            if anc_excluded:
                resolved = [c for c in resolved if c not in set(anc_excluded)]

        info = {
            "source": "feature_space_config.selected_feature_columns",
            "used_feature_space_config": True,
            "include_patterns": include_patterns,
            "exclude_patterns": exclude_patterns,
            "include_all_if_omitted": bool(include_all_if_omitted),
            "unmatched_include_patterns": unmatched_include,
            "unmatched_exclude_patterns": unmatched_exclude,
            "excluded_columns": excluded_cols,
            "ancillary_patterns": ancillary,
            "excluded_ancillary_columns": anc_excluded,
        }
        return resolved, info

    fallback = [str(c) for c in (fallback_columns or []) if str(c).strip()]
    # also remove ancillary columns from fallback
    ancillary = _extract_ancillary_columns(feature_space_cfg)
    if ancillary and fallback:
        filtered: list[str] = []
        for c in fallback:
            skip = False
            for pat in ancillary:
                if any(ch in pat for ch in ("*", "?", "[")):
                    if fnmatch.fnmatchcase(c, pat):
                        skip = True
                        break
                else:
                    if c == pat:
                        skip = True
                        break
            if not skip:
                filtered.append(c)
        fallback = filtered

    info = {
        "source": "fallback_columns",
        "used_feature_space_config": False,
        "include_patterns": [],
        "exclude_patterns": [],
        "include_all_if_omitted": False,
        "unmatched_include_patterns": [],
        "unmatched_exclude_patterns": [],
        "excluded_columns": [],
        "ancillary_patterns": ancillary,
        "excluded_ancillary_columns": [],
    }
    return fallback, info


def resolve_feature_space_group_definitions(
    *,
    available_columns: Sequence[str],
    feature_space_cfg: Mapping[str, object] | None,
) -> tuple[dict[str, dict[str, object]], dict]:
    raw_groups = feature_space_cfg.get("feature_groups", {}) if isinstance(feature_space_cfg, Mapping) else {}
    if not isinstance(raw_groups, Mapping):
        raw_groups = {}

    resolved_groups: dict[str, dict[str, object]] = {}
    info: dict[str, object] = {
        "source": "feature_space_config.feature_groups",
        "used_feature_space_config": bool(raw_groups),
        "groups": {},
    }

    for raw_name, raw_value in raw_groups.items():
        name = str(raw_name).strip()
        if not name or not isinstance(raw_value, Mapping):
            continue

        enabled = _as_bool(raw_value.get("enabled", True), default=True)
        section_present, include_patterns, exclude_patterns, include_all_if_omitted = _coerce_column_section(
            raw_value.get("feature_columns")
        )
        if section_present:
            resolved_cols, unmatched_include, unmatched_exclude, excluded_cols = _resolve_glob_patterns(
                available_columns,
                include_patterns=include_patterns,
                exclude_patterns=exclude_patterns,
                include_all_if_omitted=include_all_if_omitted,
            )
        else:
            resolved_cols = []
            unmatched_include = []
            unmatched_exclude = []
            excluded_cols = []

        group_cfg = {
            str(k): v
            for k, v in raw_value.items()
            if str(k) != "feature_columns"
        }
        group_cfg["enabled"] = bool(enabled)
        group_cfg["feature_columns"] = list(resolved_cols)
        resolved_groups[name] = group_cfg
        info["groups"][name] = {
            "enabled": bool(enabled),
            "include_patterns": include_patterns,
            "exclude_patterns": exclude_patterns,
            "include_all_if_omitted": bool(include_all_if_omitted),
            "resolved_feature_columns": list(resolved_cols),
            "unmatched_include_patterns": unmatched_include,
            "unmatched_exclude_patterns": unmatched_exclude,
            "excluded_columns": excluded_cols,
        }

    return resolved_groups, info


def resolve_feature_space_transform_options(
    *,
    feature_space_cfg: Mapping[str, object] | None,
    default_tt_prefix_priority: Sequence[str],
) -> dict:
    raw = feature_space_cfg.get("transformations", {}) if isinstance(feature_space_cfg, Mapping) else {}
    if not isinstance(raw, Mapping):
        raw = {}
    return {
        "derive_canonical_global_rate": _as_bool(raw.get("derive_canonical_global_rate", True), default=True),
        "derive_empirical_efficiencies": _as_bool(raw.get("derive_empirical_efficiencies", True), default=True),
        "derive_physics_helpers": _as_bool(raw.get("derive_physics_helpers", True), default=True),
        "derive_post_tt_plane_aggregates": _as_bool(raw.get("derive_post_tt_plane_aggregates", False), default=False),
        "keep_only_best_tt_prefix": _as_bool(raw.get("keep_only_best_tt_prefix", True), default=True),
        "tt_prefix_priority": _normalize_priority_list(
            raw.get("tt_prefix_priority", None),
            default=default_tt_prefix_priority,
        ),
    }
