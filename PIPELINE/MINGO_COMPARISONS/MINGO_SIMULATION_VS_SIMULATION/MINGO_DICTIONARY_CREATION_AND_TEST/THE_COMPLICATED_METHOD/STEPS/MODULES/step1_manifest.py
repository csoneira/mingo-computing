#!/usr/bin/env python3
"""
Shared STEP 1 feature-manifest helpers.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping, Sequence


STEP1_FEATURE_MANIFEST_FILENAME = "feature_space_manifest.json"


def _normalize_column_list(raw: object) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        text = raw.strip()
        return [text] if text else []
    if isinstance(raw, Mapping):
        out: list[str] = []
        for key, value in raw.items():
            if str(key).strip().startswith("_"):
                continue
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


def _dedupe(columns: Sequence[object]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in columns:
        text = str(raw).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def load_step1_feature_manifest(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def write_step1_feature_manifest(path: Path, manifest: Mapping[str, object]) -> None:
    path.write_text(json.dumps(dict(manifest), indent=2), encoding="utf-8")


def build_step1_feature_manifest(
    *,
    input_csv: str | Path | None,
    output_csv: str | Path | None,
    ancillary_csv: str | Path | None,
    feature_space_config_path: str | Path | None,
    feature_space_config_loaded: bool,
    input_columns: Sequence[str],
    output_columns: Sequence[str],
    primary_feature_columns: Sequence[str],
    ancillary_columns: Sequence[str],
    general_passthrough_columns: Sequence[str],
    parameter_passthrough_columns: Sequence[str],
    legacy_passthrough_columns: Sequence[str],
    declared_feature_dimensions: Sequence[str],
    declared_new_dimensions: Sequence[str],
) -> dict:
    output_cols = _dedupe(output_columns)
    output_set = set(output_cols)

    primary = [c for c in _dedupe(primary_feature_columns) if c in output_set]
    ancillary = [c for c in _dedupe(ancillary_columns) if c in output_set]
    general = [c for c in _dedupe(general_passthrough_columns) if c in output_set]
    parameter = [c for c in _dedupe(parameter_passthrough_columns) if c in output_set]
    legacy = [c for c in _dedupe(legacy_passthrough_columns) if c in output_set]
    runtime = _dedupe([*general, *parameter, *legacy])
    declared_features = _dedupe(declared_feature_dimensions)
    declared_new = _dedupe(declared_new_dimensions)
    input_cols = _dedupe(input_columns)
    dropped_from_input = [c for c in input_cols if c not in output_set]

    return {
        "schema_version": 1,
        "source_step": "1.2",
        "artifacts": {
            "input_csv": str(input_csv) if input_csv is not None else None,
            "output_csv": str(output_csv) if output_csv is not None else None,
            "ancillary_csv": str(ancillary_csv) if ancillary_csv is not None else None,
        },
        "config": {
            "feature_space_config_path": (
                str(feature_space_config_path)
                if feature_space_config_path is not None
                else None
            ),
            "feature_space_config_loaded": bool(feature_space_config_loaded),
        },
        "counts": {
            "input_columns": int(len(input_cols)),
            "materialized_columns": int(len(output_cols)),
            "primary_feature_columns": int(len(primary)),
            "ancillary_columns": int(len(ancillary)),
            "general_passthrough_columns": int(len(general)),
            "parameter_passthrough_columns": int(len(parameter)),
            "runtime_passthrough_columns": int(len(runtime)),
            "declared_feature_dimensions": int(len(declared_features)),
        },
        "columns": {
            "input_columns": input_cols,
            "materialized_columns": output_cols,
            "primary_feature_columns": primary,
            "ancillary_columns": ancillary,
            "general_passthrough_columns": general,
            "parameter_passthrough_columns": parameter,
            "legacy_passthrough_columns": legacy,
            "runtime_passthrough_columns": runtime,
            "declared_feature_dimensions": declared_features,
            "declared_new_dimensions": declared_new,
            "dropped_from_input_columns": dropped_from_input,
        },
        "counts": {
            "input_columns": int(len(input_cols)),
            "materialized_columns": int(len(output_cols)),
            "primary_feature_columns": int(len(primary)),
            "ancillary_columns": int(len(ancillary)),
            "general_passthrough_columns": int(len(general)),
            "parameter_passthrough_columns": int(len(parameter)),
            "legacy_passthrough_columns": int(len(legacy)),
            "runtime_passthrough_columns": int(len(runtime)),
            "dropped_from_input_columns": int(len(dropped_from_input)),
        },
    }


def _columns_section(manifest: Mapping[str, object] | None, key: str) -> list[str]:
    if not isinstance(manifest, Mapping):
        return []
    raw_columns = manifest.get("columns", {})
    if not isinstance(raw_columns, Mapping):
        return []
    return _dedupe(_normalize_column_list(raw_columns.get(key)))


def _filter_available(columns: Sequence[str], available_columns: Sequence[str] | None) -> list[str]:
    out = _dedupe(columns)
    if available_columns is None:
        return out
    available = {str(col).strip() for col in available_columns if str(col).strip()}
    return [c for c in out if c in available]


def manifest_primary_feature_columns(
    manifest: Mapping[str, object] | None,
    *,
    available_columns: Sequence[str] | None = None,
) -> list[str]:
    return _filter_available(
        _columns_section(manifest, "primary_feature_columns"),
        available_columns,
    )


def manifest_ancillary_columns(
    manifest: Mapping[str, object] | None,
    *,
    available_columns: Sequence[str] | None = None,
) -> list[str]:
    return _filter_available(
        _columns_section(manifest, "ancillary_columns"),
        available_columns,
    )


def manifest_general_passthrough_columns(
    manifest: Mapping[str, object] | None,
    *,
    available_columns: Sequence[str] | None = None,
) -> list[str]:
    return _filter_available(
        _columns_section(manifest, "general_passthrough_columns"),
        available_columns,
    )


def manifest_parameter_passthrough_columns(
    manifest: Mapping[str, object] | None,
    *,
    available_columns: Sequence[str] | None = None,
) -> list[str]:
    return _filter_available(
        _columns_section(manifest, "parameter_passthrough_columns"),
        available_columns,
    )


def manifest_materialized_columns(
    manifest: Mapping[str, object] | None,
    *,
    available_columns: Sequence[str] | None = None,
) -> list[str]:
    return _filter_available(
        _columns_section(manifest, "materialized_columns"),
        available_columns,
    )


def manifest_target_columns(
    manifest: Mapping[str, object] | None,
    *,
    include_primary_features: bool = True,
    include_ancillary: bool = False,
    include_general_passthrough: bool = False,
    include_parameter_passthrough: bool = False,
    include_legacy_passthrough: bool = False,
    available_columns: Sequence[str] | None = None,
) -> list[str]:
    if not isinstance(manifest, Mapping):
        return []

    materialized = manifest_materialized_columns(manifest, available_columns=available_columns)
    if not materialized:
        materialized = _dedupe(
            [
                *manifest_primary_feature_columns(manifest, available_columns=available_columns),
                *manifest_ancillary_columns(manifest, available_columns=available_columns),
                *manifest_general_passthrough_columns(manifest, available_columns=available_columns),
                *manifest_parameter_passthrough_columns(manifest, available_columns=available_columns),
                *_filter_available(
                    _columns_section(manifest, "legacy_passthrough_columns"),
                    available_columns,
                ),
            ]
        )

    desired: set[str] = set()
    if include_primary_features:
        desired.update(manifest_primary_feature_columns(manifest, available_columns=available_columns))
    if include_ancillary:
        desired.update(manifest_ancillary_columns(manifest, available_columns=available_columns))
    if include_general_passthrough:
        desired.update(
            manifest_general_passthrough_columns(manifest, available_columns=available_columns)
        )
    if include_parameter_passthrough:
        desired.update(
            manifest_parameter_passthrough_columns(manifest, available_columns=available_columns)
        )
    if include_legacy_passthrough:
        desired.update(
            _filter_available(
                _columns_section(manifest, "legacy_passthrough_columns"),
                available_columns,
            )
        )

    return [col for col in materialized if col in desired]


def primary_feature_columns_from_manifest(
    manifest: Mapping[str, object] | None,
    *,
    available_columns: Sequence[str] | None = None,
) -> list[str]:
    return manifest_primary_feature_columns(
        manifest,
        available_columns=available_columns,
    )
