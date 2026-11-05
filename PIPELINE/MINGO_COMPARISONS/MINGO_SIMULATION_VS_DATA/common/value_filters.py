#!/usr/bin/env python3
"""Shared row-level value filters for FILEvFILE validation tools."""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import Any, Sequence

import pandas as pd


NULL_LIKE_VALUES = (None, "", "null", "None")


@dataclass(frozen=True)
class ValueFilterRule:
    pattern: str
    min_value: float | None
    max_value: float | None


@dataclass(frozen=True)
class ResolvedValueFilterRule:
    pattern: str
    columns: tuple[str, ...]
    min_value: float | None
    max_value: float | None


def parse_value_filters(raw: object, *, config_key: str = "value_filters") -> list[ValueFilterRule]:
    if raw in (None, "", [], "null", "None"):
        return []
    if not isinstance(raw, list):
        raise ValueError(
            f"Config key '{config_key}' must be a JSON array of filter rules. "
            "Each rule can be ['column_pattern', min, max] or "
            "{'column': 'pattern', 'min': ..., 'max': ...}."
        )
    return [_parse_single_value_filter(item, index=index, config_key=config_key) for index, item in enumerate(raw, start=1)]


def _parse_single_value_filter(item: object, *, index: int, config_key: str) -> ValueFilterRule:
    pattern_raw: object
    min_raw: object
    max_raw: object
    if isinstance(item, dict):
        pattern_raw = item.get("column_pattern", item.get("column", item.get("pattern")))
        bounds = item.get("bounds", item.get("range"))
        if bounds is not None:
            if not isinstance(bounds, (list, tuple)) or len(bounds) != 2:
                raise ValueError(
                    f"Config key '{config_key}' rule #{index} has invalid 'bounds'; "
                    "expected a two-element list [min, max]."
                )
            min_raw, max_raw = bounds
        else:
            min_raw = item.get("min")
            max_raw = item.get("max")
    elif isinstance(item, (list, tuple)):
        if len(item) != 3:
            raise ValueError(
                f"Config key '{config_key}' rule #{index} must contain exactly "
                "three items: ['column_pattern', min, max]."
            )
        pattern_raw, min_raw, max_raw = item
    else:
        raise ValueError(
            f"Config key '{config_key}' rule #{index} must be either a list "
            "['column_pattern', min, max] or an object."
        )

    pattern = str(pattern_raw).strip()
    if not pattern or pattern in {"None", "null"}:
        raise ValueError(f"Config key '{config_key}' rule #{index} is missing a valid column pattern.")

    min_value = _optional_float(min_raw, config_key=config_key, index=index, bound_name="min")
    max_value = _optional_float(max_raw, config_key=config_key, index=index, bound_name="max")
    if min_value is None and max_value is None:
        raise ValueError(
            f"Config key '{config_key}' rule #{index} must define at least one bound "
            "('min' or 'max')."
        )
    if min_value is not None and max_value is not None and min_value > max_value:
        raise ValueError(f"Config key '{config_key}' rule #{index} must satisfy min <= max.")
    return ValueFilterRule(pattern=pattern, min_value=min_value, max_value=max_value)


def _optional_float(raw: object, *, config_key: str, index: int, bound_name: str) -> float | None:
    if raw in NULL_LIKE_VALUES:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Config key '{config_key}' rule #{index} has an invalid {bound_name} bound: {raw!r}."
        ) from exc


def resolve_value_filters(
    filters: Sequence[ValueFilterRule],
    *,
    sim_columns: Sequence[str],
    real_columns: Sequence[str],
    config_key: str = "value_filters",
) -> list[ResolvedValueFilterRule]:
    resolved: list[ResolvedValueFilterRule] = []
    sim_column_names = [str(column) for column in sim_columns]
    real_column_names = [str(column) for column in real_columns]
    for index, rule in enumerate(filters, start=1):
        sim_matches = tuple(sorted(column for column in sim_column_names if fnmatchcase(column, rule.pattern)))
        real_matches = tuple(sorted(column for column in real_column_names if fnmatchcase(column, rule.pattern)))
        if not sim_matches and not real_matches:
            raise KeyError(
                f"Config key '{config_key}' rule #{index} pattern '{rule.pattern}' "
                "did not match any columns in either parquet."
            )
        if sim_matches != real_matches:
            raise KeyError(
                f"Config key '{config_key}' rule #{index} pattern '{rule.pattern}' matched "
                f"different columns in simulation and study parquets: sim={list(sim_matches)} "
                f"study={list(real_matches)}."
            )
        resolved.append(
            ResolvedValueFilterRule(
                pattern=rule.pattern,
                columns=sim_matches,
                min_value=rule.min_value,
                max_value=rule.max_value,
            )
        )
    return resolved


def apply_resolved_value_filters(frame: pd.DataFrame, filters: Sequence[ResolvedValueFilterRule]) -> pd.DataFrame:
    if not filters:
        return frame
    keep_mask = pd.Series(True, index=frame.index, dtype=bool)
    for rule in filters:
        for column in rule.columns:
            numeric = pd.to_numeric(frame[column], errors="coerce")
            column_mask = numeric.notna()
            if rule.min_value is not None:
                column_mask &= numeric >= float(rule.min_value)
            if rule.max_value is not None:
                column_mask &= numeric <= float(rule.max_value)
            keep_mask &= column_mask
    return frame.loc[keep_mask].copy()


def apply_config_value_filters(
    sim_df: pd.DataFrame,
    real_df: pd.DataFrame,
    raw_filters: object,
    *,
    config_key: str = "value_filters",
) -> tuple[pd.DataFrame, pd.DataFrame, list[ResolvedValueFilterRule]]:
    parsed = parse_value_filters(raw_filters, config_key=config_key)
    resolved = resolve_value_filters(
        parsed,
        sim_columns=sim_df.columns,
        real_columns=real_df.columns,
        config_key=config_key,
    )
    if not resolved:
        return sim_df, real_df, []
    return (
        apply_resolved_value_filters(sim_df, resolved),
        apply_resolved_value_filters(real_df, resolved),
        resolved,
    )


def format_resolved_value_filters(filters: Sequence[ResolvedValueFilterRule]) -> str:
    parts: list[str] = []
    for rule in filters:
        lower = "-inf" if rule.min_value is None else f"{float(rule.min_value):g}"
        upper = "+inf" if rule.max_value is None else f"{float(rule.max_value):g}"
        columns_text = ",".join(rule.columns)
        parts.append(f"{rule.pattern} -> [{columns_text}] in [{lower}, {upper}]")
    return "; ".join(parts)
