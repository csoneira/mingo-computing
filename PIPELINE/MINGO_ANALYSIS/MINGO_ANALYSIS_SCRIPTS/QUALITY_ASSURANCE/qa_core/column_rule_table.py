"""Pattern-based CSV rule tables for QA plotting and threshold selection."""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
import csv
from typing import Any


_WILDCARD_CHARS = "*?["


def _parse_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    text = str(value).strip().lower()
    if not text:
        return default
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(f"Invalid boolean value '{value}'.")


def _parse_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return float(text)


def _parse_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return int(text)


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
class ColumnRule:
    """One CSV rule row for metadata columns."""

    pattern: str
    figure: str = ""
    plot_enabled: bool = True
    quality_enabled: bool = False
    center_method: str | None = None
    tolerance_mode: str | None = None
    tolerance_value: float | None = None
    lower_tolerance_value: float | None = None
    upper_tolerance_value: float | None = None
    min_samples: int | None = None
    reference_zero_policy: str | None = None
    notes: str = ""
    row_index: int = 0

    def matches(self, column_name: str) -> bool:
        return fnmatch(column_name, self.pattern)

    @property
    def is_default(self) -> bool:
        return self.pattern == "*"

    @property
    def sort_key(self) -> tuple[int, int, int, int, int]:
        specificity = _pattern_specificity(self.pattern)
        return (*specificity, -self.row_index)


def load_column_rule_table(csv_path: Path) -> list[ColumnRule]:
    """Load a CSV rule table from disk."""
    if not csv_path.exists():
        raise FileNotFoundError(f"Column rule CSV not found: {csv_path}")

    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"Column rule CSV is missing a header: {csv_path}")

        rules: list[ColumnRule] = []
        for row_index, row in enumerate(reader, start=1):
            pattern = str(row.get("pattern", "")).strip()
            if not pattern:
                continue
            rules.append(
                ColumnRule(
                    pattern=pattern,
                    figure=str(row.get("figure", "")).strip(),
                    plot_enabled=_parse_bool(row.get("plot_enabled"), default=True),
                    quality_enabled=_parse_bool(row.get("quality_enabled"), default=False),
                    center_method=str(row.get("center_method", "")).strip() or None,
                    tolerance_mode=str(row.get("tolerance_mode", "")).strip() or None,
                    tolerance_value=_parse_optional_float(row.get("tolerance_value")),
                    lower_tolerance_value=_parse_optional_float(row.get("lower_tolerance_value")),
                    upper_tolerance_value=_parse_optional_float(row.get("upper_tolerance_value")),
                    min_samples=_parse_optional_int(row.get("min_samples")),
                    reference_zero_policy=str(row.get("reference_zero_policy", "")).strip() or None,
                    notes=str(row.get("notes", "")).strip(),
                    row_index=row_index,
                )
            )

    return rules


def split_default_rule(rules: list[ColumnRule]) -> tuple[ColumnRule | None, list[ColumnRule]]:
    """Split a rule table into default and non-default rules."""
    default_rule: ColumnRule | None = None
    specific_rules: list[ColumnRule] = []
    for rule in rules:
        if rule.is_default:
            if default_rule is None or rule.row_index > default_rule.row_index:
                default_rule = rule
            continue
        specific_rules.append(rule)
    specific_rules = sorted(specific_rules, key=lambda rule: rule.sort_key, reverse=True)
    return default_rule, specific_rules


def resolve_column_rule(column_name: str, rules: list[ColumnRule]) -> ColumnRule | None:
    """Resolve one column name to the most specific rule, layered over the default row."""
    default_rule, specific_rules = split_default_rule(rules)
    best_rule = next((rule for rule in specific_rules if rule.matches(column_name)), None)

    if default_rule is None:
        return best_rule
    if best_rule is None:
        return default_rule

    return ColumnRule(
        pattern=best_rule.pattern,
        figure=best_rule.figure or default_rule.figure,
        plot_enabled=best_rule.plot_enabled,
        quality_enabled=best_rule.quality_enabled,
        center_method=best_rule.center_method or default_rule.center_method,
        tolerance_mode=best_rule.tolerance_mode or default_rule.tolerance_mode,
        tolerance_value=best_rule.tolerance_value if best_rule.tolerance_value is not None else default_rule.tolerance_value,
        lower_tolerance_value=(
            best_rule.lower_tolerance_value
            if best_rule.lower_tolerance_value is not None
            else default_rule.lower_tolerance_value
        ),
        upper_tolerance_value=(
            best_rule.upper_tolerance_value
            if best_rule.upper_tolerance_value is not None
            else default_rule.upper_tolerance_value
        ),
        min_samples=best_rule.min_samples if best_rule.min_samples is not None else default_rule.min_samples,
        reference_zero_policy=best_rule.reference_zero_policy or default_rule.reference_zero_policy,
        notes=best_rule.notes or default_rule.notes,
        row_index=best_rule.row_index,
    )


def rule_to_threshold_mapping(rule: ColumnRule) -> dict[str, Any]:
    """Convert a resolved CSV rule into a threshold-rule mapping."""
    out: dict[str, Any] = {}
    if rule.center_method:
        out["center_method"] = rule.center_method
    if rule.tolerance_mode:
        out["tolerance_mode"] = rule.tolerance_mode
    if rule.tolerance_value is not None:
        out["tolerance_value"] = rule.tolerance_value
    if rule.lower_tolerance_value is not None:
        out["lower_tolerance_value"] = rule.lower_tolerance_value
    if rule.upper_tolerance_value is not None:
        out["upper_tolerance_value"] = rule.upper_tolerance_value
    if rule.min_samples is not None:
        out["min_samples"] = rule.min_samples
    if rule.reference_zero_policy:
        out["reference_zero_policy"] = rule.reference_zero_policy
    return out


def matches_any_pattern(column_name: str, patterns: list[str]) -> bool:
    """Return whether a column matches any literal or wildcard pattern."""
    return any(fnmatch(column_name, pattern) for pattern in patterns if pattern)
