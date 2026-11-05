"""Column category resolution for QUALITY_ASSURANCE_NEW."""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from typing import Any

import pandas as pd

CATEGORY_IGNORE = "ignore"
CATEGORY_PLOT_ONLY = "plot_only"
CATEGORY_QUALITY_ONLY = "quality_only"
CATEGORY_QUALITY_AND_PLOT = "quality_and_plot"
VALID_CATEGORIES = (
    CATEGORY_QUALITY_AND_PLOT,
    CATEGORY_QUALITY_ONLY,
    CATEGORY_PLOT_ONLY,
    CATEGORY_IGNORE,
)
_CATEGORY_PRIORITY = {
    CATEGORY_IGNORE: 3,
    CATEGORY_QUALITY_AND_PLOT: 2,
    CATEGORY_QUALITY_ONLY: 1,
    CATEGORY_PLOT_ONLY: 0,
}
_WILDCARD_CHARS = "*?["


def _has_wildcard(pattern: str) -> bool:
    return any(char in pattern for char in _WILDCARD_CHARS)


def _pattern_specificity(pattern: str) -> tuple[int, int, int, int]:
    if pattern == "*":
        return (0, 0, 0, 0)
    literal_chars = len(pattern.replace("*", "").replace("?", "").replace("[", "").replace("]", ""))
    wildcard_count = pattern.count("*") + pattern.count("?") + pattern.count("[")
    exact = 1 if not _has_wildcard(pattern) else 0
    return (1, exact, literal_chars, -wildcard_count)


@dataclass(frozen=True)
class CategoryRule:
    pattern: str
    category: str
    row_index: int

    def matches(self, column_name: str) -> bool:
        return fnmatch(column_name, self.pattern)

    @property
    def sort_key(self) -> tuple[int, int, int, int, int, int]:
        specificity = _pattern_specificity(self.pattern)
        return (*specificity, _CATEGORY_PRIORITY[self.category], -self.row_index)


def load_category_config(path: Any) -> dict[str, list[str]]:
    if isinstance(path, dict):
        raw = path
    else:
        from .common import load_yaml_mapping

        raw = load_yaml_mapping(path)

    config: dict[str, list[str]] = {}
    for category in VALID_CATEGORIES:
        values = raw.get(category, [])
        if values is None:
            values = []
        if not isinstance(values, list):
            raise ValueError(f"'{category}' must be a YAML list.")
        config[category] = [str(value).strip() for value in values if str(value).strip()]
    return config


def category_rules(
    category_config: dict[str, list[str]],
    *,
    common_ignore_patterns: list[str] | None = None,
) -> list[CategoryRule]:
    rules: list[CategoryRule] = []
    row_index = 0
    for pattern in common_ignore_patterns or []:
        row_index += 1
        rules.append(CategoryRule(pattern=str(pattern).strip(), category=CATEGORY_IGNORE, row_index=row_index))
    for category in VALID_CATEGORIES:
        for pattern in category_config.get(category, []):
            row_index += 1
            rules.append(CategoryRule(pattern=pattern, category=category, row_index=row_index))
    return rules


def resolve_column_category(column_name: str, rules: list[CategoryRule]) -> str:
    matched = [rule for rule in rules if rule.matches(column_name)]
    if column_name.endswith("_limit"):
        shorthand_quality_matches = [
            rule
            for rule in rules
            if rule.category in {CATEGORY_QUALITY_AND_PLOT, CATEGORY_QUALITY_ONLY}
            and not _has_wildcard(rule.pattern)
            and column_name.endswith(f"_{rule.pattern}_limit")
        ]
        matched.extend(shorthand_quality_matches)
    if not matched:
        return CATEGORY_PLOT_ONLY
    best = sorted(matched, key=lambda rule: rule.sort_key, reverse=True)[0]
    return best.category


def is_numeric_candidate(series: pd.Series) -> bool:
    numeric = pd.to_numeric(series, errors="coerce")
    return bool(numeric.notna().any())


def build_column_manifest(
    df: pd.DataFrame,
    category_config: dict[str, list[str]],
    *,
    common_ignore_patterns: list[str] | None = None,
) -> pd.DataFrame:
    rules = category_rules(category_config, common_ignore_patterns=common_ignore_patterns)
    records: list[dict[str, Any]] = []
    for column_name in df.columns:
        requested_category = resolve_column_category(column_name, rules)
        numeric_candidate = is_numeric_candidate(df[column_name])
        effective_plot = requested_category in {CATEGORY_PLOT_ONLY, CATEGORY_QUALITY_AND_PLOT} and numeric_candidate
        effective_quality = requested_category in {CATEGORY_QUALITY_ONLY, CATEGORY_QUALITY_AND_PLOT} and numeric_candidate
        note = ""
        if requested_category != CATEGORY_IGNORE and not numeric_candidate:
            note = "non_numeric"
        records.append(
            {
                "column_name": column_name,
                "requested_category": requested_category,
                "is_numeric_candidate": int(numeric_candidate),
                "effective_plot": int(effective_plot),
                "effective_quality": int(effective_quality),
                "note": note,
            }
        )
    return pd.DataFrame(records).sort_values("column_name").reset_index(drop=True)


def manifest_plot_columns(
    manifest_df: pd.DataFrame, *, quality_and_plot_only: bool = False,
) -> list[str]:
    """Return plottable columns, optionally restricted to QA-driving plots."""
    if manifest_df.empty:
        return []
    mask = manifest_df["effective_plot"] == 1
    if quality_and_plot_only:
        mask &= manifest_df["requested_category"] == CATEGORY_QUALITY_AND_PLOT
    return manifest_df.loc[mask, "column_name"].astype(str).tolist()


def manifest_quality_columns(manifest_df: pd.DataFrame) -> list[str]:
    if manifest_df.empty:
        return []
    return manifest_df.loc[manifest_df["effective_quality"] == 1, "column_name"].astype(str).tolist()
