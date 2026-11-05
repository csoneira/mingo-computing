from __future__ import annotations

import ast
import logging
import operator
import re
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from feature_space_config import resolve_feature_space_transform_options

LOG = logging.getLogger(__name__)

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
DEFAULT_POST_TT_AGGREGATE_TWO_PLANE_LABELS = ("12", "13", "14", "23", "24", "34")
DEFAULT_POST_TT_AGGREGATE_THREE_PLANE_LABELS = ("123", "124", "134", "234")
DEFAULT_POST_TT_AGGREGATE_FOUR_PLANE_LABEL = "1234"

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


def normalize_requested_columns(raw: object) -> list[str]:
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


def coerce_bool(value: object, default: bool = False) -> bool:
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


def normalize_tt_label(label: object) -> str:
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


def ensure_efficiency_columns(df: pd.DataFrame) -> pd.DataFrame:
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


def build_prefix_global_rate_columns(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, str], dict[str, list[str]]]:
    by_prefix: dict[str, list[str]] = {}
    for col in df.columns:
        match = TT_RATE_COLUMN_RE.match(str(col))
        if match is None:
            continue
        prefix = str(match.group("prefix")).strip()
        label = normalize_tt_label(match.group("label"))
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


def select_canonical_global_rate(
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


def ensure_standard_task_prefix_rate_columns(
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


def compute_empirical_efficiencies(
    df: pd.DataFrame,
    *,
    preferred_prefixes: tuple[str, ...],
) -> tuple[pd.DataFrame, str | None, list[str]]:
    out = df.copy()
    all_prefixes: list[str] = []
    seen: set[str] = set()
    for prefix in preferred_prefixes:
        if prefix not in seen:
            all_prefixes.append(prefix)
            seen.add(prefix)
    for prefix in sorted(
        set(
            str(match.group("prefix")).strip()
            for col in out.columns
            for match in [TT_RATE_COLUMN_RE.match(str(col))]
            if match
        )
    ):
        if prefix not in seen:
            all_prefixes.append(prefix)
            seen.add(prefix)

    required_labels = ("1234", "234", "134", "124", "123")
    per_plane_missing = {1: "234", 2: "134", 3: "124", 4: "123"}

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
        needed = [f"{prefix}_{label}_rate_hz" for label in required_labels]
        if not all(col in out.columns for col in needed):
            continue

        n_four = pd.to_numeric(out[four_col], errors="coerce")
        any_plane_used = False
        for plane in (1, 2, 3, 4):
            miss_col = f"{prefix}_{per_plane_missing[plane]}_rate_hz"
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


def add_derived_physics_helper_columns(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, int]:
    out = ensure_efficiency_columns(df)
    if not all(col in out.columns for col in ("eff_p1", "eff_p2", "eff_p3", "eff_p4")):
        return out, 0

    eff_df = out[["eff_p1", "eff_p2", "eff_p3", "eff_p4"]].apply(pd.to_numeric, errors="coerce")
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
        label = normalize_tt_label(item)
        if label not in CANONICAL_TT_LABELS or label in seen:
            continue
        seen.add(label)
        out.append(label)
    if not out:
        out = [str(label) for label in default if str(label) in CANONICAL_TT_LABELS]
    return out


def resolve_post_tt_plane_aggregate_config(
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
        "four_plane_label": normalize_tt_label(
            raw.get("four_plane_label", DEFAULT_POST_TT_AGGREGATE_FOUR_PLANE_LABEL)
        )
        or DEFAULT_POST_TT_AGGREGATE_FOUR_PLANE_LABEL,
    }


def add_post_tt_plane_aggregate_columns(
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
        clean_labels = [str(label).strip() for label in labels if str(label).strip()]
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


def backfill_efficiency_columns_from_empirical(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    out = df.copy()
    created = 0
    for idx in (1, 2, 3, 4):
        emp_col = f"eff_empirical_{idx}"
        ep_col = f"eff_p{idx}"
        es_col = f"eff_sim_{idx}"
        if emp_col not in out.columns:
            continue

        emp_vals = pd.to_numeric(out[emp_col], errors="coerce")

        if ep_col not in out.columns:
            out[ep_col] = emp_vals
            created += 1
        else:
            ep_vals = pd.to_numeric(out[ep_col], errors="coerce")
            fill_ep = ep_vals.isna() & emp_vals.notna()
            if bool(fill_ep.any()):
                out.loc[fill_ep, ep_col] = emp_vals.loc[fill_ep]

        ep_vals_now = pd.to_numeric(out[ep_col], errors="coerce")
        if es_col not in out.columns:
            out[es_col] = ep_vals_now
            created += 1
        else:
            es_vals = pd.to_numeric(out[es_col], errors="coerce")
            fill_es = es_vals.isna() & ep_vals_now.notna()
            if bool(fill_es.any()):
                out.loc[fill_es, es_col] = ep_vals_now.loc[fill_es]

    return out, created


def resolve_column_transformations(
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
    enabled = coerce_bool(raw.get("enabled", True), default=True)
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
                    text = str(sub_expr).strip()
                    if name and text:
                        new_dimensions[name] = text
                continue
            name = str(key).strip()
            text = str(expr).strip()
            if name and text:
                new_dimensions[name] = text
    enabled = bool(enabled) and (bool(keep_dimensions) or bool(new_dimensions))
    return {
        "enabled": enabled,
        "keep_dimensions": keep_dimensions,
        "new_dimensions": new_dimensions,
    }


def evaluate_column_expression(
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


def apply_column_transformations(
    df: pd.DataFrame,
    *,
    transform_cfg: Mapping[str, object],
    logger: logging.Logger | None = None,
) -> tuple[pd.DataFrame, dict[str, object], list[str]]:
    out = df.copy()
    info: dict[str, object] = {
        "enabled": True,
        "keep_dimensions": list(transform_cfg.get("keep_dimensions", [])),
        "new_dimensions": dict(transform_cfg.get("new_dimensions", {})),
        "applied": False,
    }
    missing_keep: list[str] = []
    log = logger or LOG

    new_dims = transform_cfg.get("new_dimensions", {})
    if isinstance(new_dims, Mapping):
        for name, expr in new_dims.items():
            try:
                out[name] = evaluate_column_expression(df=out, expression=str(expr))
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


def select_best_tt_prefix(
    available_prefixes: set[str],
    *,
    priority: tuple[str, ...],
) -> str | None:
    for prefix in priority:
        if prefix in available_prefixes:
            return prefix
    if available_prefixes:
        return sorted(available_prefixes)[0]
    return None


def drop_non_best_tt_columns(
    df: pd.DataFrame,
    *,
    best_prefix: str | None,
    tt_cols_by_prefix: dict[str, list[str]],
    rate_col_by_prefix: dict[str, str],
) -> tuple[pd.DataFrame, list[str]]:
    if best_prefix is None:
        return df, []
    drop_set: set[str] = set()
    for prefix, cols in tt_cols_by_prefix.items():
        if prefix == best_prefix:
            continue
        drop_set.update(col for col in cols if col in df.columns)
    for _prefix, rate_col in rate_col_by_prefix.items():
        if rate_col in df.columns:
            drop_set.add(rate_col)
    drop_cols = list(drop_set)
    if not drop_cols:
        return df, []
    return df.drop(columns=drop_cols), drop_cols


def filter_rows_with_complete_numeric_columns(
    df: pd.DataFrame,
    *,
    required_columns: Sequence[str],
) -> tuple[pd.DataFrame, dict[str, object]]:
    resolved_required = [
        str(col).strip()
        for col in required_columns
        if str(col).strip() and str(col).strip() in df.columns
    ]
    if not resolved_required:
        return df.reset_index(drop=True), {
            "enabled": False,
            "input_rows": int(len(df)),
            "rows_kept": int(len(df)),
            "rows_removed": 0,
            "rows_removed_fraction": 0.0,
            "required_columns_checked": [],
            "required_columns_checked_count": 0,
            "row_missing_required_column_count_distribution": {"0": int(len(df))},
            "top_missing_required_columns": [],
        }

    feature_frame = (
        df[resolved_required]
        .apply(pd.to_numeric, errors="coerce")
        .replace([np.inf, -np.inf], np.nan)
    )
    missing_by_row = feature_frame.isna().sum(axis=1)
    valid_mask = missing_by_row.eq(0)
    filtered = df.loc[valid_mask].copy().reset_index(drop=True)

    missing_distribution = (
        missing_by_row.value_counts(dropna=False)
        .sort_index()
        .astype(int)
        .to_dict()
    )
    missing_by_column = feature_frame.isna().sum(axis=0)
    missing_by_column_df = pd.DataFrame(
        {
            "column": [str(col) for col in missing_by_column.index],
            "missing_rows": [int(count) for count in missing_by_column.to_numpy()],
        }
    )
    missing_by_column_df = missing_by_column_df.loc[
        missing_by_column_df["missing_rows"] > 0
    ].sort_values(
        by=["missing_rows", "column"],
        ascending=[False, True],
    )
    input_rows = int(len(df))
    rows_kept = int(len(filtered))
    rows_removed = int(input_rows - rows_kept)
    rows_removed_fraction = (rows_removed / input_rows) if input_rows > 0 else 0.0

    return filtered, {
        "enabled": True,
        "input_rows": input_rows,
        "rows_kept": rows_kept,
        "rows_removed": rows_removed,
        "rows_removed_fraction": float(rows_removed_fraction),
        "required_columns_checked": list(resolved_required),
        "required_columns_checked_count": int(len(resolved_required)),
        "row_missing_required_column_count_distribution": {
            str(int(key)): int(value)
            for key, value in missing_distribution.items()
        },
        "top_missing_required_columns": missing_by_column_df.head(20).to_dict(orient="records"),
    }


def apply_feature_space_transform(
    df: pd.DataFrame,
    *,
    cfg_12: Mapping[str, object] | None,
    feature_space_cfg: Mapping[str, object] | None,
    default_tt_prefix_priority: Sequence[str] = CANONICAL_PREFIX_PRIORITY,
    backfill_efficiency_from_empirical_enabled: bool = False,
    logger: logging.Logger | None = None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    log = logger or LOG
    out = ensure_efficiency_columns(df)
    transform_options = resolve_feature_space_transform_options(
        feature_space_cfg=feature_space_cfg or {},
        default_tt_prefix_priority=default_tt_prefix_priority,
    )
    column_transform_cfg = resolve_column_transformations(
        feature_space_cfg=feature_space_cfg or {},
    )
    transform_options = dict(transform_options)
    transform_options["column_transformations"] = bool(column_transform_cfg.get("enabled", False))
    post_tt_aggregate_cfg = resolve_post_tt_plane_aggregate_config(
        feature_space_cfg=feature_space_cfg or {},
    )
    preferred_prefixes_t = tuple(transform_options["tt_prefix_priority"])

    out, rate_col_by_prefix, tt_cols_by_prefix = build_prefix_global_rate_columns(out)
    out, added_standard_rate_cols = ensure_standard_task_prefix_rate_columns(
        out,
        rate_col_by_prefix=rate_col_by_prefix,
    )

    canonical_source_counts: dict[str, int] = {}
    if transform_options["derive_canonical_global_rate"]:
        out, canonical_source_counts = select_canonical_global_rate(
            out,
            rate_col_by_prefix=rate_col_by_prefix,
            preferred_prefixes=preferred_prefixes_t,
        )

    empirical_selected_prefix = None
    empirical_used_prefixes: list[str] = []
    if transform_options["derive_empirical_efficiencies"]:
        out, empirical_selected_prefix, empirical_used_prefixes = compute_empirical_efficiencies(
            out,
            preferred_prefixes=preferred_prefixes_t,
        )

    helper_count = 0
    if transform_options["derive_physics_helpers"]:
        out, helper_count = add_derived_physics_helper_columns(out)

    post_tt_plane_aggregates_info: dict[str, object] = {
        "enabled": False,
        "source_prefix": str(post_tt_aggregate_cfg.get("source_prefix", "post_tt")),
        "columns": {},
    }
    if (
        bool(transform_options.get("derive_post_tt_plane_aggregates", False))
        and bool(post_tt_aggregate_cfg.get("enabled", True))
    ):
        out, post_tt_plane_aggregates_info = add_post_tt_plane_aggregate_columns(
            out,
            aggregate_cfg=post_tt_aggregate_cfg,
        )

    cfg = cfg_12 if isinstance(cfg_12, Mapping) else {}
    try:
        min_eff_sim = float(cfg.get("min_simulated_efficiency", 0.5))
    except (TypeError, ValueError):
        min_eff_sim = 0.5
    try:
        max_eff_spread = float(cfg.get("max_simulated_efficiency_spread", 0.15))
    except (TypeError, ValueError):
        max_eff_spread = 0.15

    eff_sim_cols = [c for c in ("eff_sim_1", "eff_sim_2", "eff_sim_3", "eff_sim_4") if c in out.columns]
    rows_before_min_eff_filter = int(len(out))
    rows_removed_min_eff_filter = 0
    if eff_sim_cols and min_eff_sim > 0.0:
        eff_vals = out[eff_sim_cols].apply(pd.to_numeric, errors="coerce")
        keep_mask = (eff_vals >= min_eff_sim).all(axis=1)
        rows_removed_min_eff_filter = int(np.count_nonzero(~keep_mask))
        out = out.loc[keep_mask].reset_index(drop=True)

    rows_before_spread_filter = int(len(out))
    rows_removed_spread_filter = 0
    if eff_sim_cols and max_eff_spread > 0.0:
        eff_vals = out[eff_sim_cols].apply(pd.to_numeric, errors="coerce")
        spread = eff_vals.max(axis=1) - eff_vals.min(axis=1)
        keep_mask = spread <= max_eff_spread
        rows_removed_spread_filter = int(np.count_nonzero(~keep_mask))
        out = out.loc[keep_mask].reset_index(drop=True)

    backfilled_efficiency_columns = 0
    if backfill_efficiency_from_empirical_enabled:
        out, backfilled_efficiency_columns = backfill_efficiency_columns_from_empirical(out)
        if transform_options["derive_physics_helpers"]:
            out, helper_count_post = add_derived_physics_helper_columns(out)
            helper_count += int(helper_count_post)

    column_transform_info: dict[str, object] = {"enabled": False}
    missing_keep_dimensions: list[str] = []
    if column_transform_cfg.get("enabled", False):
        out, column_transform_info, missing_keep_dimensions = apply_column_transformations(
            out,
            transform_cfg=column_transform_cfg,
            logger=log,
        )

    return out, {
        "transform_options": dict(transform_options),
        "column_transform_cfg": dict(column_transform_cfg),
        "column_transform_info": column_transform_info,
        "missing_keep_dimensions": list(missing_keep_dimensions),
        "preferred_prefixes": list(preferred_prefixes_t),
        "rate_col_by_prefix": dict(rate_col_by_prefix),
        "tt_cols_by_prefix": {k: list(v) for k, v in tt_cols_by_prefix.items()},
        "added_standard_rate_cols": list(added_standard_rate_cols),
        "canonical_source_counts": dict(canonical_source_counts),
        "empirical_selected_prefix": empirical_selected_prefix,
        "empirical_used_prefixes": list(empirical_used_prefixes),
        "helper_count": int(helper_count),
        "post_tt_plane_aggregates_info": post_tt_plane_aggregates_info,
        "min_simulated_efficiency": float(min_eff_sim),
        "max_simulated_efficiency_spread": float(max_eff_spread),
        "eff_sim_cols": list(eff_sim_cols),
        "rows_before_min_eff_filter": int(rows_before_min_eff_filter),
        "rows_removed_min_eff_filter": int(rows_removed_min_eff_filter),
        "rows_before_spread_filter": int(rows_before_spread_filter),
        "rows_removed_spread_filter": int(rows_removed_spread_filter),
        "backfilled_efficiency_columns": int(backfilled_efficiency_columns),
    }
