"""Helpers for building epoch references and evaluating metadata values against them."""

from __future__ import annotations

from ast import literal_eval
from dataclasses import dataclass
import re
from typing import Any, Mapping

import numpy as np
import pandas as pd

from .thresholds import ThresholdRule, evaluate_value, select_threshold_rule

EPOCH_REFERENCE_METADATA_COLUMNS = (
    "station_name",
    "epoch_id",
    "conf_number",
    "start_date",
    "end_date",
    "location",
    "comment",
    "boundary_overlap",
)
COMPONENT_COLUMN_RE = re.compile(r"^(?P<source>.+)__([0-9]+)$")


@dataclass(frozen=True)
class EvaluationColumnSpec:
    """Description of one scalar QA observable."""

    evaluation_column: str
    source_column: str
    component_index: int | None = None


def _parse_vector_value(value: Any) -> np.ndarray | None:
    if value is None:
        return None
    if isinstance(value, float) and np.isnan(value):
        return None

    parsed: Any
    if isinstance(value, (list, tuple, np.ndarray)):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            parsed = literal_eval(text)
        except (SyntaxError, ValueError):
            return None

    if not isinstance(parsed, (list, tuple, np.ndarray)):
        return None

    out: list[float] = []
    for item in parsed:
        try:
            out.append(float(item))
        except (TypeError, ValueError):
            out.append(np.nan)
    return np.asarray(out, dtype=float)


def _component_spec(column_name: str) -> tuple[str, int] | None:
    match = COMPONENT_COLUMN_RE.match(str(column_name))
    if match is None:
        return None
    try:
        return match.group("source"), int(match.group(2))
    except (TypeError, ValueError):
        return None


def _iqr(values: np.ndarray) -> float:
    if values.size == 0:
        return float("nan")
    q1, q3 = np.percentile(values, [25, 75])
    return float(q3 - q1)


def _mad(values: np.ndarray, center: float) -> float:
    if values.size == 0:
        return float("nan")
    return float(np.median(np.abs(values - center)))


def _std(values: np.ndarray) -> float:
    if values.size == 0:
        return float("nan")
    return float(np.std(values, ddof=0))


def _reference_values_for_rule(values: np.ndarray, rule: ThresholdRule) -> tuple[np.ndarray, int]:
    if rule.reference_zero_policy != "drop_zeros_unless_all_zero":
        return values, 0

    nonzero_values = values[values != 0]
    if nonzero_values.size == 0:
        return values, 0
    return nonzero_values, int(values.size - nonzero_values.size)


def build_scalar_value_frame(
    df: pd.DataFrame,
    columns: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Expand numeric and vector-valued metadata columns into scalar QA columns."""
    scalar_columns: dict[str, Any] = {}
    specs: list[EvaluationColumnSpec] = []

    for column_name in columns:
        if column_name not in df.columns:
            continue

        numeric = pd.to_numeric(df[column_name], errors="coerce")
        if numeric.notna().any():
            component = _component_spec(column_name)
            source_column = component[0] if component is not None else column_name
            component_index = component[1] if component is not None else None
            scalar_columns[column_name] = numeric.astype(float)
            specs.append(EvaluationColumnSpec(column_name, source_column, component_index))
            continue

        parsed = [_parse_vector_value(item) for item in df[column_name].tolist()]
        max_len = max((len(arr) for arr in parsed if arr is not None), default=0)
        if max_len == 0:
            continue

        matrix = np.full((len(parsed), max_len), np.nan, dtype=float)
        for row_idx, arr in enumerate(parsed):
            if arr is None:
                continue
            matrix[row_idx, : len(arr)] = arr

        for component_index in range(max_len):
            evaluation_column = f"{column_name}__{component_index}"
            scalar_columns[evaluation_column] = matrix[:, component_index]
            specs.append(EvaluationColumnSpec(evaluation_column, column_name, component_index))

    value_frame = pd.DataFrame(scalar_columns, index=df.index)
    specs_df = pd.DataFrame(
        [
            {
                "evaluation_column": spec.evaluation_column,
                "source_column": spec.source_column,
                "component_index": spec.component_index,
            }
            for spec in specs
        ]
    )
    return value_frame, specs_df


def build_epoch_reference_table(
    value_frame: pd.DataFrame,
    specs_df: pd.DataFrame,
    epoch_ids: pd.Series,
    *,
    defaults: Mapping[str, Any] | ThresholdRule | None = None,
    column_rules: Mapping[str, Mapping[str, Any] | ThresholdRule] | None = None,
) -> pd.DataFrame:
    """Compute per-epoch reference centers and scale metrics for scalar QA columns."""
    epoch_series = pd.Series(epoch_ids, index=value_frame.index, dtype="string")
    records: list[dict[str, Any]] = []

    for spec in specs_df.to_dict("records"):
        evaluation_column = spec["evaluation_column"]
        if evaluation_column not in value_frame.columns:
            continue

        working = pd.DataFrame(
            {
                "epoch_id": epoch_series,
                "value": pd.to_numeric(value_frame[evaluation_column], errors="coerce"),
            }
        )
        working = working[working["epoch_id"].notna() & working["value"].notna()]
        if working.empty:
            continue

        for epoch_id, group in working.groupby("epoch_id", sort=True):
            values = group["value"].to_numpy(dtype=float)
            rule = select_threshold_rule(
                evaluation_column,
                defaults=defaults,
                column_rules=column_rules,
            )
            reference_values, ignored_zero_count = _reference_values_for_rule(values, rule)
            center_median = float(np.median(reference_values))
            center_mean = float(np.mean(reference_values))
            records.append(
                {
                    "epoch_id": epoch_id,
                    "evaluation_column": evaluation_column,
                    "source_column": spec["source_column"],
                    "component_index": spec["component_index"],
                    "n_raw_values": int(values.size),
                    "n_values": int(reference_values.size),
                    "n_zero_values_ignored": ignored_zero_count,
                    "reference_zero_policy": rule.reference_zero_policy,
                    "center_median": center_median,
                    "center_mean": center_mean,
                    "scale_mad": _mad(reference_values, center_median),
                    "scale_iqr": _iqr(reference_values),
                    "scale_std": _std(reference_values),
                }
            )

    return pd.DataFrame(records)


def build_epoch_reference_wide_table(
    reference_df: pd.DataFrame,
    *,
    value_column: str = "center_median",
) -> pd.DataFrame:
    """Pivot a long epoch-reference table into one row per epoch."""
    required_columns = {"epoch_id", "evaluation_column", value_column}
    if reference_df.empty or not required_columns <= set(reference_df.columns):
        return pd.DataFrame()

    metadata_columns = [column for column in EPOCH_REFERENCE_METADATA_COLUMNS if column in reference_df.columns]
    if "epoch_id" not in metadata_columns:
        metadata_columns.insert(0, "epoch_id")

    grouped = reference_df.groupby("epoch_id", dropna=False)
    metadata_agg = grouped[metadata_columns].agg(
        lambda values: next((value for value in values if pd.notna(value)), pd.NA)
    )
    if "epoch_id" not in metadata_agg.columns:
        metadata_agg.insert(0, "epoch_id", metadata_agg.index)
    metadata_agg = metadata_agg.reset_index(drop=True)

    wide_values = (
        reference_df.pivot_table(
            index="epoch_id",
            columns="evaluation_column",
            values=value_column,
            aggfunc="first",
        )
        .reset_index()
    )
    wide_values.columns.name = None

    out = metadata_agg.merge(wide_values, on="epoch_id", how="left")
    sort_key = None
    if "start_date" in out.columns:
        parsed = pd.to_datetime(out["start_date"], errors="coerce")
        if parsed.notna().any():
            out["__sort_start_date__"] = parsed
            sort_key = "__sort_start_date__"
    out = out.sort_values(sort_key or "epoch_id", na_position="last").reset_index(drop=True)
    if "__sort_start_date__" in out.columns:
        out = out.drop(columns="__sort_start_date__")
    return out


def evaluate_scalar_frame(
    base_df: pd.DataFrame,
    value_frame: pd.DataFrame,
    reference_df: pd.DataFrame,
    *,
    defaults: Mapping[str, Any] | ThresholdRule | None = None,
    column_rules: Mapping[str, Mapping[str, Any] | ThresholdRule] | None = None,
) -> pd.DataFrame:
    """Evaluate scalar QA columns row-by-row against epoch references."""
    if reference_df.empty or value_frame.empty:
        return pd.DataFrame(
            columns=[
                "filename_base",
                "epoch_id",
                "evaluation_column",
                "source_column",
                "component_index",
                "value",
                "status",
                "reason",
                "reference_center",
                "reference_scale",
                "reference_scale_kind",
                "reference_n_values",
                "lower_bound",
                "upper_bound",
                "rule_center_method",
                "rule_tolerance_mode",
                "rule_tolerance_value",
                "rule_min_samples",
                "deviation",
            ]
        )

    reference_lookup: dict[tuple[str, str], dict[str, Any]] = {}
    spec_lookup: dict[str, dict[str, Any]] = {}
    for row in reference_df.to_dict("records"):
        reference_lookup[(str(row["epoch_id"]), str(row["evaluation_column"]))] = row
        spec_lookup[str(row["evaluation_column"])] = {
            "source_column": row["source_column"],
            "component_index": row["component_index"],
        }

    records: list[dict[str, Any]] = []
    for row_index, base_row in base_df.iterrows():
        filename_base = str(base_row.get("filename_base", "")).strip()
        epoch_id = base_row.get("epoch_id")
        if pd.isna(epoch_id):
            continue
        epoch_token = str(epoch_id)

        for evaluation_column in value_frame.columns:
            value = pd.to_numeric(pd.Series([value_frame.at[row_index, evaluation_column]]), errors="coerce").iloc[0]
            if pd.isna(value):
                continue

            spec = spec_lookup.get(evaluation_column, {})
            rule = select_threshold_rule(
                evaluation_column,
                defaults=defaults,
                column_rules=column_rules,
            )
            reference = reference_lookup.get((epoch_token, evaluation_column))
            if reference is None:
                records.append(
                    {
                        "filename_base": filename_base,
                        "epoch_id": epoch_token,
                        "evaluation_column": evaluation_column,
                        "source_column": spec.get("source_column", evaluation_column),
                        "component_index": spec.get("component_index"),
                        "value": float(value),
                        "status": "missing_reference",
                        "reason": "missing_reference",
                        "reference_center": np.nan,
                        "reference_scale": np.nan,
                        "reference_scale_kind": "",
                        "reference_n_values": 0,
                        "lower_bound": np.nan,
                        "upper_bound": np.nan,
                        "rule_center_method": rule.center_method,
                        "rule_tolerance_mode": rule.tolerance_mode,
                        "rule_tolerance_value": rule.tolerance_value,
                        "rule_min_samples": rule.min_samples,
                        "deviation": np.nan,
                    }
                )
                continue

            if int(reference["n_values"]) < rule.min_samples:
                records.append(
                    {
                        "filename_base": filename_base,
                        "epoch_id": epoch_token,
                        "evaluation_column": evaluation_column,
                        "source_column": reference["source_column"],
                        "component_index": reference["component_index"],
                        "value": float(value),
                        "status": "insufficient_reference",
                        "reason": "insufficient_reference",
                        "reference_center": np.nan,
                        "reference_scale": np.nan,
                        "reference_scale_kind": "",
                        "reference_n_values": int(reference["n_values"]),
                        "lower_bound": np.nan,
                        "upper_bound": np.nan,
                        "rule_center_method": rule.center_method,
                        "rule_tolerance_mode": rule.tolerance_mode,
                        "rule_tolerance_value": rule.tolerance_value,
                        "rule_min_samples": rule.min_samples,
                        "deviation": np.nan,
                    }
                )
                continue

            if rule.center_method == "mean":
                reference_center = float(reference["center_mean"])
            else:
                reference_center = float(reference["center_median"])

            scale_kind = ""
            reference_scale: float | None = None
            if rule.tolerance_mode == "mad_multiplier":
                reference_scale = float(reference["scale_mad"])
                scale_kind = "mad"
            elif rule.tolerance_mode == "iqr_multiplier":
                reference_scale = float(reference["scale_iqr"])
                scale_kind = "iqr"
            elif rule.tolerance_mode == "zscore":
                reference_scale = float(reference["scale_std"])
                scale_kind = "std"

            result = evaluate_value(value, reference_center, rule, scale=reference_scale)
            status = result.status if result.status in {"pass", "fail"} else "invalid_rule"
            records.append(
                {
                    "filename_base": filename_base,
                    "epoch_id": epoch_token,
                    "evaluation_column": evaluation_column,
                    "source_column": reference["source_column"],
                    "component_index": reference["component_index"],
                    "value": float(value),
                    "status": status,
                    "reason": result.reason or status,
                    "reference_center": reference_center,
                    "reference_scale": np.nan if reference_scale is None else float(reference_scale),
                    "reference_scale_kind": scale_kind,
                    "reference_n_values": int(reference["n_values"]),
                    "lower_bound": np.nan if result.lower is None else float(result.lower),
                    "upper_bound": np.nan if result.upper is None else float(result.upper),
                    "rule_center_method": rule.center_method,
                    "rule_tolerance_mode": rule.tolerance_mode,
                    "rule_tolerance_value": rule.tolerance_value,
                    "rule_min_samples": rule.min_samples,
                    "deviation": np.nan if result.deviation is None else float(result.deviation),
                }
            )

    return pd.DataFrame(records)
