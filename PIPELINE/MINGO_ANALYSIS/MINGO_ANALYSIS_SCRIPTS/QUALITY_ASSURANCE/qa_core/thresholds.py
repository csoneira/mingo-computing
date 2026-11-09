"""Threshold rule helpers for epoch-aware QUALITY_ASSURANCE decisions."""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from typing import Any, Mapping

import pandas as pd

SUPPORTED_TOLERANCE_MODES = {"relative_pct", "absolute", "mad_multiplier", "iqr_multiplier", "zscore"}
SUPPORTED_REFERENCE_ZERO_POLICIES = {"keep", "drop_zeros_unless_all_zero"}


def _tolerance_from_mapping(
    mapping: Mapping[str, Any],
    *,
    value_key: str,
    percent_key: str,
    default: float | None,
) -> float | None:
    """Read a fractional tolerance, preferring a human-readable percent key."""
    percent = mapping.get(percent_key)
    if percent is not None:
        percent_value = float(percent)
        if percent_value < 0:
            raise ValueError(f"{percent_key} cannot be negative.")
        return percent_value / 100.0
    raw_value = mapping.get(value_key, default)
    return None if raw_value is None else float(raw_value)


@dataclass(frozen=True)
class ThresholdRule:
    """Rule describing how to build lower/upper limits around a reference center."""

    center_method: str = "median"
    tolerance_mode: str = "relative_pct"
    tolerance_value: float = 0.10
    lower_tolerance_value: float | None = None
    upper_tolerance_value: float | None = None
    min_samples: int = 8
    reference_zero_policy: str = "keep"

    def __post_init__(self) -> None:
        if self.tolerance_mode not in SUPPORTED_TOLERANCE_MODES:
            raise ValueError(
                f"Unsupported tolerance_mode '{self.tolerance_mode}'. "
                f"Supported: {sorted(SUPPORTED_TOLERANCE_MODES)}"
            )
        if self.reference_zero_policy not in SUPPORTED_REFERENCE_ZERO_POLICIES:
            raise ValueError(
                f"Unsupported reference_zero_policy '{self.reference_zero_policy}'. "
                f"Supported: {sorted(SUPPORTED_REFERENCE_ZERO_POLICIES)}"
            )
        if self.tolerance_value < 0:
            raise ValueError("tolerance_value cannot be negative.")
        if self.min_samples < 1:
            raise ValueError("min_samples must be >= 1.")
        if self.lower_tolerance_value is not None and self.lower_tolerance_value < 0:
            raise ValueError("lower_tolerance_value cannot be negative.")
        if self.upper_tolerance_value is not None and self.upper_tolerance_value < 0:
            raise ValueError("upper_tolerance_value cannot be negative.")

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any] | None = None) -> "ThresholdRule":
        """Build a rule from a configuration mapping."""
        mapping = dict(mapping or {})
        return cls(
            center_method=str(mapping.get("center_method", "median")).strip() or "median",
            tolerance_mode=str(mapping.get("tolerance_mode", "relative_pct")).strip() or "relative_pct",
            tolerance_value=float(_tolerance_from_mapping(
                mapping, value_key="tolerance_value",
                percent_key="tolerance_percent", default=0.10,
            )),
            lower_tolerance_value=_tolerance_from_mapping(
                mapping, value_key="lower_tolerance_value",
                percent_key="lower_tolerance_percent", default=None,
            ),
            upper_tolerance_value=_tolerance_from_mapping(
                mapping, value_key="upper_tolerance_value",
                percent_key="upper_tolerance_percent", default=None,
            ),
            min_samples=int(mapping.get("min_samples", 8)),
            reference_zero_policy=str(mapping.get("reference_zero_policy", "keep")).strip() or "keep",
        )


@dataclass(frozen=True)
class ThresholdEvaluation:
    """Evaluation result for one value against one threshold rule."""

    lower: float | None
    upper: float | None
    status: str
    deviation: float | None
    reason: str | None = None


def resolve_threshold_rule(
    defaults: Mapping[str, Any] | ThresholdRule | None,
    override: Mapping[str, Any] | ThresholdRule | None = None,
) -> ThresholdRule:
    """Merge defaults with optional overrides into one rule."""
    base = defaults if isinstance(defaults, ThresholdRule) else ThresholdRule.from_mapping(defaults)
    if override is None:
        return base
    if isinstance(override, ThresholdRule):
        return override

    merged = {
        "center_method": base.center_method,
        "tolerance_mode": base.tolerance_mode,
        "tolerance_value": base.tolerance_value,
        "lower_tolerance_value": base.lower_tolerance_value,
        "upper_tolerance_value": base.upper_tolerance_value,
        "min_samples": base.min_samples,
        "reference_zero_policy": base.reference_zero_policy,
    }
    merged.update(dict(override))
    return ThresholdRule.from_mapping(merged)


def select_threshold_rule(
    column_name: str,
    *,
    defaults: Mapping[str, Any] | ThresholdRule | None = None,
    column_rules: Mapping[str, Mapping[str, Any] | ThresholdRule] | None = None,
) -> ThresholdRule:
    """Resolve the threshold rule for one column using exact or glob matches."""
    if column_rules:
        if column_name in column_rules:
            return resolve_threshold_rule(defaults, column_rules[column_name])
        for pattern, rule in column_rules.items():
            if fnmatch(column_name, pattern):
                return resolve_threshold_rule(defaults, rule)
    return resolve_threshold_rule(defaults)


def compute_bounds(center: float, rule: ThresholdRule, *, scale: float | None = None) -> tuple[float, float]:
    """Compute lower/upper bounds for a reference center."""
    center_value = float(center)
    if pd.isna(center_value):
        raise ValueError("center must be finite.")

    if rule.tolerance_mode == "relative_pct":
        lower_value = rule.lower_tolerance_value if rule.lower_tolerance_value is not None else rule.tolerance_value
        upper_value = rule.upper_tolerance_value if rule.upper_tolerance_value is not None else rule.tolerance_value
        magnitude = abs(center_value)
        if magnitude == 0:
            lower_delta = lower_value
            upper_delta = upper_value
        else:
            lower_delta = magnitude * lower_value
            upper_delta = magnitude * upper_value
    elif rule.tolerance_mode == "absolute":
        lower_delta = rule.lower_tolerance_value if rule.lower_tolerance_value is not None else rule.tolerance_value
        upper_delta = rule.upper_tolerance_value if rule.upper_tolerance_value is not None else rule.tolerance_value
    else:
        if scale is None:
            raise ValueError(f"scale is required for tolerance_mode='{rule.tolerance_mode}'.")
        scale_value = abs(float(scale))
        if pd.isna(scale_value):
            raise ValueError("scale must be finite.")
        lower_multiplier = (
            rule.lower_tolerance_value if rule.lower_tolerance_value is not None else rule.tolerance_value
        )
        upper_multiplier = (
            rule.upper_tolerance_value if rule.upper_tolerance_value is not None else rule.tolerance_value
        )
        lower_delta = scale_value * lower_multiplier
        upper_delta = scale_value * upper_multiplier

    lower = center_value - lower_delta
    upper = center_value + upper_delta
    return (min(lower, upper), max(lower, upper))


def evaluate_value(
    value: Any,
    center: Any,
    rule: ThresholdRule,
    *,
    scale: float | None = None,
) -> ThresholdEvaluation:
    """Evaluate one scalar value against a threshold rule."""
    if value is None or center is None:
        return ThresholdEvaluation(lower=None, upper=None, status="missing", deviation=None)

    value_float = float(value)
    center_float = float(center)
    if pd.isna(value_float) or pd.isna(center_float):
        return ThresholdEvaluation(lower=None, upper=None, status="missing", deviation=None)

    try:
        lower, upper = compute_bounds(center_float, rule, scale=scale)
    except ValueError as exc:
        return ThresholdEvaluation(lower=None, upper=None, status="invalid_rule", deviation=None, reason=str(exc))

    if lower <= value_float <= upper:
        return ThresholdEvaluation(lower=lower, upper=upper, status="pass", deviation=0.0)
    if value_float < lower:
        return ThresholdEvaluation(
            lower=lower,
            upper=upper,
            status="fail",
            deviation=value_float - lower,
            reason="below_lower_bound",
        )
    return ThresholdEvaluation(
        lower=lower,
        upper=upper,
        status="fail",
        deviation=value_float - upper,
        reason="above_upper_bound",
    )
