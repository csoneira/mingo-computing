#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent
REPO_ROOT = ROOT_DIR.parents[4]
OUTPUT_DIR = ROOT_DIR / "OUTPUTS"
FILES_DIR = OUTPUT_DIR / "FILES"
PLOTS_DIR = OUTPUT_DIR / "PLOTS"
DEFAULT_CONFIG_PATH = ROOT_DIR / "config.json"

CANONICAL_EFF_COLUMNS = ["eff_empirical_1", "eff_empirical_2", "eff_empirical_3", "eff_empirical_4"]
TT_TWO_PLANE_LABELS = ["12", "13", "14", "23", "24", "34"]
TT_THREE_PLANE_LABELS = ["123", "124", "134", "234"]
TT_FOUR_PLANE_LABEL = "1234"
TT_RATE_LABELS = TT_TWO_PLANE_LABELS + TT_THREE_PLANE_LABELS + [TT_FOUR_PLANE_LABEL]
TT_THREE_TO_FOUR_MISSING_BY_PLANE = {1: "234", 2: "134", 3: "124", 4: "123"}
TASK_FINAL_STAGE_PREFIX = {1: "clean_tt", 2: "cal_tt", 3: "list_tt", 4: "fit_tt", 5: "post_tt"}
TRIGGER_METADATA_SOURCE_ALIASES = {
    "trigger": "trigger_type",
    "trigger_type": "trigger_type",
    "robust": "robust_efficiency",
    "robust_eff": "robust_efficiency",
    "robust_efficiency": "robust_efficiency",
}
TRIGGER_RATE_FAMILY_TO_COLUMN = {
    "total": "total_rate_hz",
    "four_plane": "four_plane_rate_hz",
    "three_plane": "three_plane_rate_hz",
    "two_plane": "two_plane_rate_hz",
    "three_and_four_plane": "three_and_four_plane_rate_hz",
    "two_and_three_plane": "two_and_three_plane_rate_hz",
}
TRIGGER_RATE_FAMILY_ALIASES = {
    "global": "total",
    "all": "total",
    "total_rate": "total",
    "rate_total": "total",
    "total_rate_hz": "total",
    "rate_total_hz": "total",
    "1234": "four_plane",
    "4": "four_plane",
    "four_plane_rate": "four_plane",
    "rate_1234": "four_plane",
    "four_plane_rate_hz": "four_plane",
    "rate_1234_hz": "four_plane",
    "3": "three_plane",
    "three_plane_rate": "three_plane",
    "three_plane_rate_hz": "three_plane",
    "2": "two_plane",
    "two_plane_rate": "two_plane",
    "two_plane_rate_hz": "two_plane",
    "34": "three_and_four_plane",
    "three_and_four_plane_rate": "three_and_four_plane",
    "three_and_four_plane_rate_hz": "three_and_four_plane",
    "23": "two_and_three_plane",
    "two_and_three_plane_rate": "two_and_three_plane",
    "two_and_three_plane_rate_hz": "two_and_three_plane",
}
ROBUST_RATE_FAMILY_TO_COLUMN = {
    "total": "total_rate_hz",
    "four_plane": "four_plane_rate_hz",
    "four_plane_robust_hz": "four_plane_robust_hz",
}
ROBUST_RATE_FAMILY_TO_SOURCE_COLUMN = {
    "total": "rate_total_hz",
    "four_plane": "rate_1234_hz",
    "four_plane_robust_hz": "four_plane_robust_hz",
}
ROBUST_RATE_FAMILY_TO_COUNT_COLUMN = {
    "total": "total_count",
    "four_plane": "four_plane_count",
    "four_plane_robust_hz": "four_plane_robust_count",
}
ROBUST_RATE_FAMILY_ALIASES = {
    "global": "total",
    "all": "total",
    "total_rate": "total",
    "rate_total": "total",
    "total_rate_hz": "total",
    "rate_total_hz": "total",
    "1234": "four_plane",
    "4": "four_plane",
    "four_plane_rate": "four_plane",
    "rate_1234": "four_plane",
    "four_plane_rate_hz": "four_plane",
    "rate_1234_hz": "four_plane",
    "four_plane_robust": "four_plane_robust_hz",
    "four_plane_robust_rate": "four_plane_robust_hz",
    "four_plane_robust_rate_hz": "four_plane_robust_hz",
    "four_plane_robust_hz": "four_plane_robust_hz",
}
ROBUST_OPTIONAL_COUNT_COLUMNS = {
    "total": ["total_count", "count_total", "rate_total_count"],
    "four_plane": ["four_plane_count", "count_1234", "rate_1234_count"],
    "four_plane_robust_hz": ["four_plane_robust_count", "four_plane_robust_count_union", "count_four_plane_robust"],
}
ROBUST_DIAGNOSTIC_COLUMNS = [
    "four_plane_robust_count_union",
    "four_plane_robust_count_intersection",
    "four_plane_robust_hz_union",
    "four_plane_robust_hz_intersection",
]
ROBUST_EFFICIENCY_VARIANT_TO_SUFFIX = {
    "default": "",
    "robust_xyphi": "",
    "plateau": "_plateau",
    "overall": "_overall",
    "median_x": "_median_x",
}
ROBUST_EFFICIENCY_VARIANT_ALIASES = {
    "": "default",
    "default": "default",
    "base": "default",
    "plain": "default",
    "nominal": "default",
    "eff": "default",
    "robust_xyphi": "robust_xyphi",
    "xyphi": "robust_xyphi",
    "fiducial": "robust_xyphi",
    "fiducial_xyphi": "robust_xyphi",
    "plateau": "plateau",
    "overall": "overall",
    "median_x": "median_x",
    "median": "median_x",
    "x_median": "median_x",
}
DEFAULT_ROBUST_EFFICIENCY_TASK_ID = 4


def ensure_output_dirs() -> None:
    FILES_DIR.mkdir(parents=True, exist_ok=True)
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    config_path = Path(path or DEFAULT_CONFIG_PATH).resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["_config_path"] = str(config_path)
    config["_config_dir"] = str(config_path.parent)
    return config


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def resolve_path(config: dict[str, Any], raw_path: str | Path) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return (Path(config["_config_dir"]) / path).resolve()


def cfg_path(config: dict[str, Any], *keys: str) -> Path:
    value: Any = config
    for key in keys:
        value = value[key]
    return resolve_path(config, value)


def _normalize_optional_int(value: Any) -> int | None:
    if value in (None, "", "null", "None"):
        return None
    return int(value)


def _normalize_optional_str(value: Any) -> str | None:
    if value in (None, "", "null", "None"):
        return None
    text = str(value).strip()
    return text or None


def get_trigger_type_selection(config: dict[str, Any]) -> dict[str, Any]:
    raw = config.get("trigger_type_selection", {})
    if not isinstance(raw, dict):
        raw = {}

    metadata_source_raw = str(raw.get("metadata_source", "trigger_type")).strip().lower()
    metadata_source = TRIGGER_METADATA_SOURCE_ALIASES.get(metadata_source_raw, metadata_source_raw)
    if metadata_source == "robust_efficiency":
        efficiency_variant_raw = str(raw.get("robust_efficiency_variant", "default")).strip().lower()
        efficiency_variant = ROBUST_EFFICIENCY_VARIANT_ALIASES.get(efficiency_variant_raw, efficiency_variant_raw)
        if efficiency_variant not in ROBUST_EFFICIENCY_VARIANT_TO_SUFFIX:
            raise ValueError(
                "Unsupported trigger_type_selection.robust_efficiency_variant: "
                f"{raw.get('robust_efficiency_variant')!r}. Supported values are: "
                + ", ".join(sorted(ROBUST_EFFICIENCY_VARIANT_TO_SUFFIX))
            )
        rate_family_text = str(raw.get("rate_family", "1234")).strip()
        if not rate_family_text:
            rate_family_text = "1234"
        rate_family_lookup = rate_family_text.lower()
        rate_family_alias = ROBUST_RATE_FAMILY_ALIASES.get(rate_family_lookup)
        selected_source_override = _normalize_optional_str(raw.get("selected_source_rate_column"))
        selected_count_override = _normalize_optional_str(raw.get("selected_count_column"))
        selected_display_label = _normalize_optional_str(raw.get("selected_display_label"))

        if selected_source_override is not None:
            rate_family = rate_family_alias or selected_source_override
            rate_family_column = selected_source_override
            selected_source_rate_column = selected_source_override
        elif rate_family_alias is not None:
            rate_family = rate_family_alias
            rate_family_column = ROBUST_RATE_FAMILY_TO_COLUMN[rate_family]
            selected_source_rate_column = ROBUST_RATE_FAMILY_TO_SOURCE_COLUMN[rate_family]
        else:
            rate_family = rate_family_text
            rate_family_column = rate_family_text
            selected_source_rate_column = rate_family_text

        return {
            "metadata_source": metadata_source,
            "source_name": "robust_efficiency",
            "task_id": DEFAULT_ROBUST_EFFICIENCY_TASK_ID,
            "metadata_task_id": DEFAULT_ROBUST_EFFICIENCY_TASK_ID,
            "stage_prefix": None,
            "offender_threshold": None,
            "rate_family": rate_family,
            "rate_family_column": rate_family_column,
            "selected_source_rate_column": selected_source_rate_column,
            "selected_count_column": selected_count_override,
            "selected_display_label": selected_display_label or selected_source_rate_column,
            "robust_efficiency_variant": efficiency_variant,
        }
    if metadata_source != "trigger_type":
        raise ValueError(
            "Unsupported trigger_type_selection.metadata_source: "
            f"{raw.get('metadata_source')!r}. Supported values are: trigger_type, robust_efficiency"
        )

    task_id = int(raw.get("task_id", 5))
    stage_prefix_raw = raw.get("stage_prefix")
    if stage_prefix_raw in (None, "", "null", "None"):
        stage_prefix = TASK_FINAL_STAGE_PREFIX.get(task_id)
        if stage_prefix is None:
            raise ValueError(f"Unsupported trigger_type_selection.task_id: {task_id}")
    else:
        stage_prefix = str(stage_prefix_raw).strip()

    offender_threshold = _normalize_optional_int(raw.get("offender_threshold"))

    rate_family_raw = str(raw.get("rate_family", "total")).strip().lower()
    rate_family = TRIGGER_RATE_FAMILY_ALIASES.get(rate_family_raw, rate_family_raw)
    if rate_family not in TRIGGER_RATE_FAMILY_TO_COLUMN:
        raise ValueError(
            "Unsupported trigger_type_selection.rate_family: "
            f"{raw.get('rate_family')!r}. Supported values are: "
            + ", ".join(sorted(TRIGGER_RATE_FAMILY_TO_COLUMN))
        )

    selected_source_rate_column = format_selected_rate_name(
        stage_prefix=stage_prefix,
        rate_family_column=TRIGGER_RATE_FAMILY_TO_COLUMN[rate_family],
        offender_threshold=offender_threshold,
    )
    return {
        "metadata_source": metadata_source,
        "source_name": "trigger_type",
        "task_id": task_id,
        "metadata_task_id": task_id,
        "stage_prefix": stage_prefix,
        "offender_threshold": offender_threshold,
        "rate_family": rate_family,
        "rate_family_column": TRIGGER_RATE_FAMILY_TO_COLUMN[rate_family],
        "selected_source_rate_column": selected_source_rate_column,
    }


def format_selected_rate_name(
    *,
    stage_prefix: str | None,
    rate_family_column: str,
    offender_threshold: int | None,
    metadata_source: str = "trigger_type",
) -> str:
    if str(metadata_source).strip().lower() == "robust_efficiency":
        return str(rate_family_column)
    if stage_prefix in (None, "", "null", "None"):
        return str(rate_family_column)
    if offender_threshold is None:
        return f"{stage_prefix}_{rate_family_column}"
    return f"{stage_prefix}_total_offenders_le_{int(offender_threshold)}_{rate_family_column}"


def trigger_rate_source_column(stage_prefix: str, tt_label: str, offender_threshold: int | None) -> str:
    if offender_threshold is None:
        return f"{stage_prefix}_{tt_label}_rate_hz"
    return f"{stage_prefix}_total_offenders_le_{int(offender_threshold)}_{tt_label}_rate_hz"


def trigger_count_source_column(stage_prefix: str, tt_label: str, offender_threshold: int | None) -> str | None:
    if offender_threshold is None:
        return None
    return f"{stage_prefix}_total_offenders_le_{int(offender_threshold)}_{tt_label}_count"


def _safe_sum_series(dataframe: pd.DataFrame, columns: list[str]) -> pd.Series:
    if not columns:
        return pd.Series(np.nan, index=dataframe.index, dtype=float)
    numeric = dataframe[columns].apply(pd.to_numeric, errors="coerce")
    return numeric.sum(axis=1, min_count=1)


def _resolved_count_series(
    dataframe: pd.DataFrame,
    *,
    rate_column: str,
    count_column: str | None,
    denominator_column: str | None = "count_rate_denominator_seconds",
) -> pd.Series:
    if count_column and count_column in dataframe.columns:
        return pd.to_numeric(dataframe[count_column], errors="coerce")
    rate_series = pd.to_numeric(dataframe.get(rate_column), errors="coerce")
    if denominator_column is None or denominator_column not in dataframe.columns:
        return pd.Series(np.nan, index=dataframe.index, dtype=float)
    denominator = pd.to_numeric(dataframe[denominator_column], errors="coerce")
    return rate_series * denominator


def _missing_columns(dataframe: pd.DataFrame, columns: list[str]) -> list[str]:
    return [column for column in columns if column not in dataframe.columns]


def _optional_numeric_series(dataframe: pd.DataFrame, column: str | None) -> pd.Series:
    if not column or column not in dataframe.columns:
        return pd.Series(np.nan, index=dataframe.index, dtype=float)
    return pd.to_numeric(dataframe[column], errors="coerce")


def _first_present_column(dataframe: pd.DataFrame, candidates: list[str]) -> str | None:
    for column in candidates:
        if column in dataframe.columns:
            return column
    return None


def _unique_preserve(values: list[str | None]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _resolve_robust_selected_count_column(
    dataframe: pd.DataFrame,
    *,
    selection: dict[str, Any],
    total_count_source: str | None,
    four_plane_count_source: str | None,
    four_plane_robust_count_source: str | None,
) -> str | None:
    selected_source_rate_column = str(selection["selected_source_rate_column"])
    configured_count_column = _normalize_optional_str(selection.get("selected_count_column"))

    candidates: list[str | None] = [configured_count_column]
    if selected_source_rate_column.endswith("_count"):
        candidates.append(selected_source_rate_column)
    if selected_source_rate_column.endswith("_hz"):
        candidates.append(selected_source_rate_column[:-3] + "_count")
    if selected_source_rate_column.endswith("_rate_hz"):
        candidates.append(selected_source_rate_column.replace("_rate_hz", "_count"))

    if str(selection.get("rate_family")) in ROBUST_RATE_FAMILY_TO_COUNT_COLUMN:
        candidates.append(ROBUST_RATE_FAMILY_TO_COUNT_COLUMN[str(selection["rate_family"])])

    if selected_source_rate_column in {
        ROBUST_RATE_FAMILY_TO_SOURCE_COLUMN["total"],
        ROBUST_RATE_FAMILY_TO_COLUMN["total"],
    }:
        candidates.extend([total_count_source, "total_count", "rate_total_count", "count_total"])
    if selected_source_rate_column in {
        ROBUST_RATE_FAMILY_TO_SOURCE_COLUMN["four_plane"],
        ROBUST_RATE_FAMILY_TO_COLUMN["four_plane"],
    }:
        candidates.extend([four_plane_count_source, "four_plane_count", "rate_1234_count", "count_1234"])
    if selected_source_rate_column in {
        ROBUST_RATE_FAMILY_TO_SOURCE_COLUMN["four_plane_robust_hz"],
        ROBUST_RATE_FAMILY_TO_COLUMN["four_plane_robust_hz"],
    }:
        candidates.extend([four_plane_robust_count_source, "four_plane_robust_count", "count_four_plane_robust"])
    if selected_source_rate_column == "four_plane_robust_hz_union":
        candidates.append("four_plane_robust_count_union")
    if selected_source_rate_column == "four_plane_robust_hz_intersection":
        candidates.append("four_plane_robust_count_intersection")

    return _first_present_column(dataframe, _unique_preserve(candidates))


def _derive_robust_efficiency_features(
    dataframe: pd.DataFrame,
    selection: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    efficiency_variant = str(selection.get("robust_efficiency_variant", "default"))
    efficiency_suffix = ROBUST_EFFICIENCY_VARIANT_TO_SUFFIX[efficiency_variant]
    required_columns = [
        f"eff{idx}{efficiency_suffix}" for idx in range(1, 5)
    ] + [
        ROBUST_RATE_FAMILY_TO_SOURCE_COLUMN["total"],
        ROBUST_RATE_FAMILY_TO_SOURCE_COLUMN["four_plane"],
    ]
    selected_source_rate_column = str(selection["selected_source_rate_column"])
    if selected_source_rate_column not in required_columns:
        required_columns.append(selected_source_rate_column)
    missing = _missing_columns(dataframe, required_columns)
    if missing:
        raise KeyError(
            "Missing robust-efficiency columns required by trigger_type_selection: "
            + ", ".join(sorted(missing))
        )

    total_count_source = _first_present_column(dataframe, ROBUST_OPTIONAL_COUNT_COLUMNS["total"])
    four_plane_count_source = _first_present_column(dataframe, ROBUST_OPTIONAL_COUNT_COLUMNS["four_plane"])
    four_plane_robust_count_source = _first_present_column(
        dataframe,
        ROBUST_OPTIONAL_COUNT_COLUMNS["four_plane_robust_hz"],
    )
    selected_count_source = _resolve_robust_selected_count_column(
        dataframe,
        selection=selection,
        total_count_source=total_count_source,
        four_plane_count_source=four_plane_count_source,
        four_plane_robust_count_source=four_plane_robust_count_source,
    )

    out = dataframe.copy()
    out["count_rate_denominator_seconds"] = (
        pd.to_numeric(out["count_rate_denominator_seconds"], errors="coerce")
        if "count_rate_denominator_seconds" in out.columns
        else pd.Series(np.nan, index=out.index, dtype=float)
    )
    out["two_plane_rate_hz"] = pd.Series(np.nan, index=out.index, dtype=float)
    out["three_plane_rate_hz"] = pd.Series(np.nan, index=out.index, dtype=float)
    out["four_plane_rate_hz"] = pd.to_numeric(out[ROBUST_RATE_FAMILY_TO_SOURCE_COLUMN["four_plane"]], errors="coerce")
    out["four_plane_robust_hz"] = (
        pd.to_numeric(out[ROBUST_RATE_FAMILY_TO_SOURCE_COLUMN["four_plane_robust_hz"]], errors="coerce")
        if ROBUST_RATE_FAMILY_TO_SOURCE_COLUMN["four_plane_robust_hz"] in out.columns
        else pd.Series(np.nan, index=out.index, dtype=float)
    )
    out["three_and_four_plane_rate_hz"] = pd.Series(np.nan, index=out.index, dtype=float)
    out["two_and_three_plane_rate_hz"] = pd.Series(np.nan, index=out.index, dtype=float)
    out["total_rate_hz"] = pd.to_numeric(out[ROBUST_RATE_FAMILY_TO_SOURCE_COLUMN["total"]], errors="coerce")

    out["two_plane_count"] = pd.Series(np.nan, index=out.index, dtype=float)
    out["three_plane_count"] = pd.Series(np.nan, index=out.index, dtype=float)
    out["four_plane_count"] = _resolved_count_series(
        out,
        rate_column=ROBUST_RATE_FAMILY_TO_SOURCE_COLUMN["four_plane"],
        count_column=four_plane_count_source,
    )
    out["four_plane_robust_count"] = _resolved_count_series(
        out,
        rate_column=ROBUST_RATE_FAMILY_TO_SOURCE_COLUMN["four_plane_robust_hz"],
        count_column=four_plane_robust_count_source,
    )
    out["three_and_four_plane_count"] = pd.Series(np.nan, index=out.index, dtype=float)
    out["two_and_three_plane_count"] = pd.Series(np.nan, index=out.index, dtype=float)
    out["total_count"] = _resolved_count_series(
        out,
        rate_column=ROBUST_RATE_FAMILY_TO_SOURCE_COLUMN["total"],
        count_column=total_count_source,
    )
    for column_name in ROBUST_DIAGNOSTIC_COLUMNS:
        if column_name in out.columns:
            out[column_name] = pd.to_numeric(out[column_name], errors="coerce")

    efficiency_source_columns: dict[str, str] = {}
    for plane_idx in range(1, 5):
        source_column = f"eff{plane_idx}{efficiency_suffix}"
        out[f"eff_empirical_{plane_idx}"] = pd.to_numeric(out[source_column], errors="coerce")
        efficiency_source_columns[f"plane_{plane_idx}"] = source_column

    selected_rate_column = str(selection["selected_source_rate_column"])
    out["selected_rate_hz"] = pd.to_numeric(out[selected_rate_column], errors="coerce")
    out["selected_rate_count"] = _optional_numeric_series(out, selected_count_source)
    out["rate_hz"] = out["selected_rate_hz"]

    metadata = {
        "metadata_source": selection["metadata_source"],
        "source_name": selection["source_name"],
        "task_id": int(selection["task_id"]),
        "stage_prefix": None,
        "requested_stage_prefix": None,
        "used_stage_prefix": None,
        "stage_prefix_fallback_used": False,
        "requested_offender_threshold": None,
        "used_offender_threshold": None,
        "rate_family": selection["rate_family"],
        "rate_family_column": selected_rate_column,
        "selected_source_rate_column": selection["selected_source_rate_column"],
        "selected_source_count_column": selected_count_source,
        "selected_display_label": selection.get("selected_display_label"),
        "robust_efficiency_variant": efficiency_variant,
        "robust_efficiency_source_columns": efficiency_source_columns,
        "plain_column_fallback_used": False,
        "source_rate_columns": {
            "selected": selected_rate_column,
            "four_plane": ROBUST_RATE_FAMILY_TO_SOURCE_COLUMN["four_plane"],
            "four_plane_robust_hz": ROBUST_RATE_FAMILY_TO_SOURCE_COLUMN["four_plane_robust_hz"],
            "total": ROBUST_RATE_FAMILY_TO_SOURCE_COLUMN["total"],
        },
        "source_count_columns": {
            "selected": selected_count_source,
            "four_plane": four_plane_count_source,
            "four_plane_robust_hz": four_plane_robust_count_source,
            "total": total_count_source,
        },
    }
    return out, metadata


def derive_trigger_rate_features(
    dataframe: pd.DataFrame,
    config: dict[str, Any],
    *,
    allow_plain_fallback: bool = False,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    selection = get_trigger_type_selection(config)
    if str(selection.get("metadata_source", "trigger_type")) == "robust_efficiency":
        return _derive_robust_efficiency_features(dataframe, selection)

    requested_stage_prefix = str(selection["stage_prefix"])
    requested_threshold = selection["offender_threshold"]

    def _build_source_columns(stage_prefix: str, offender_threshold: int | None) -> dict[str, str]:
        return {
            label: trigger_rate_source_column(stage_prefix, label, offender_threshold)
            for label in TT_RATE_LABELS
        }

    def _missing_source_columns(source_columns: dict[str, str]) -> list[str]:
        return [column for column in source_columns.values() if column not in dataframe.columns]

    used_stage_prefix = requested_stage_prefix
    used_threshold = requested_threshold
    source_columns = _build_source_columns(used_stage_prefix, used_threshold)
    missing = _missing_source_columns(source_columns)

    if missing and allow_plain_fallback:
        fallback_stage_candidates = [
            TASK_FINAL_STAGE_PREFIX[task_id]
            for task_id in sorted(TASK_FINAL_STAGE_PREFIX.keys(), reverse=True)
            if TASK_FINAL_STAGE_PREFIX[task_id] != requested_stage_prefix
        ]

        fallback_candidates: list[tuple[str, int | None]] = []
        if requested_threshold is not None:
            fallback_candidates.append((requested_stage_prefix, None))
        fallback_candidates.extend((stage_prefix, requested_threshold) for stage_prefix in fallback_stage_candidates)
        if requested_threshold is not None:
            fallback_candidates.extend((stage_prefix, None) for stage_prefix in fallback_stage_candidates)

        for candidate_stage_prefix, candidate_threshold in fallback_candidates:
            candidate_columns = _build_source_columns(candidate_stage_prefix, candidate_threshold)
            candidate_missing = _missing_source_columns(candidate_columns)
            if candidate_missing:
                continue
            source_columns = candidate_columns
            used_stage_prefix = candidate_stage_prefix
            used_threshold = candidate_threshold
            missing = []
            break

    if missing:
        available_stage_prefixes = sorted(
            {
                column_name[: -len(f"_{tt_label}_rate_hz")]
                for column_name in dataframe.columns.astype(str)
                for tt_label in TT_RATE_LABELS
                if column_name.endswith(f"_{tt_label}_rate_hz")
            }
        )
        available_stage_hint = (
            "none detected"
            if not available_stage_prefixes
            else ", ".join(available_stage_prefixes)
        )
        raise KeyError(
            "Missing trigger-type rate columns required by trigger_type_selection: "
            + ", ".join(sorted(missing))
            + f". Requested stage_prefix={requested_stage_prefix!r}, "
            + f"offender_threshold={requested_threshold!r}. "
            + f"Available stage prefixes in dataframe: {available_stage_hint}."
        )

    count_columns = {
        label: trigger_count_source_column(used_stage_prefix, label, used_threshold)
        for label in TT_RATE_LABELS
    }

    out = dataframe.copy()
    out["count_rate_denominator_seconds"] = (
        pd.to_numeric(out["count_rate_denominator_seconds"], errors="coerce")
        if "count_rate_denominator_seconds" in out.columns
        else pd.Series(np.nan, index=out.index, dtype=float)
    )
    component_rates = {
        label: pd.to_numeric(out[trigger_rate_source_column(used_stage_prefix, label, used_threshold)], errors="coerce")
        for label in TT_RATE_LABELS
    }
    component_counts = {
        label: _resolved_count_series(
            out,
            rate_column=trigger_rate_source_column(used_stage_prefix, label, used_threshold),
            count_column=count_columns[label],
        )
        for label in TT_RATE_LABELS
    }

    out["two_plane_rate_hz"] = _safe_sum_series(
        out.assign(**{f"__{k}": v for k, v in component_rates.items()}),
        [f"__{label}" for label in TT_TWO_PLANE_LABELS],
    )
    out["three_plane_rate_hz"] = _safe_sum_series(
        out.assign(**{f"__{k}": v for k, v in component_rates.items()}),
        [f"__{label}" for label in TT_THREE_PLANE_LABELS],
    )
    out["four_plane_rate_hz"] = component_rates[TT_FOUR_PLANE_LABEL]
    out["three_and_four_plane_rate_hz"] = out["three_plane_rate_hz"] + out["four_plane_rate_hz"]
    out["two_and_three_plane_rate_hz"] = out["two_plane_rate_hz"] + out["three_plane_rate_hz"]
    out["total_rate_hz"] = out["two_plane_rate_hz"] + out["three_plane_rate_hz"] + out["four_plane_rate_hz"]

    out["two_plane_count"] = _safe_sum_series(
        out.assign(**{f"__{k}": v for k, v in component_counts.items()}),
        [f"__{label}" for label in TT_TWO_PLANE_LABELS],
    )
    out["three_plane_count"] = _safe_sum_series(
        out.assign(**{f"__{k}": v for k, v in component_counts.items()}),
        [f"__{label}" for label in TT_THREE_PLANE_LABELS],
    )
    out["four_plane_count"] = component_counts[TT_FOUR_PLANE_LABEL]
    out["four_plane_robust_count"] = pd.Series(np.nan, index=out.index, dtype=float)
    out["three_and_four_plane_count"] = out["three_plane_count"] + out["four_plane_count"]
    out["two_and_three_plane_count"] = out["two_plane_count"] + out["three_plane_count"]
    out["total_count"] = out["two_plane_count"] + out["three_plane_count"] + out["four_plane_count"]

    valid_denominator = out["four_plane_rate_hz"].where(pd.to_numeric(out["four_plane_rate_hz"], errors="coerce") > 0.0)
    for plane_idx in range(1, 5):
        numerator_label = TT_THREE_TO_FOUR_MISSING_BY_PLANE[plane_idx]
        out[f"eff_empirical_{plane_idx}"] = 1 - component_rates[numerator_label] / valid_denominator

    selected_rate_column = selection["rate_family_column"]
    selected_count_column = selected_rate_column.replace("_rate_hz", "_count")
    out["selected_rate_hz"] = out[selected_rate_column]
    out["selected_rate_count"] = out[selected_count_column]
    out["rate_hz"] = out["selected_rate_hz"]

    metadata = {
        "metadata_source": selection["metadata_source"],
        "source_name": selection["source_name"],
        "task_id": int(selection["task_id"]),
        "stage_prefix": used_stage_prefix,
        "requested_stage_prefix": requested_stage_prefix,
        "used_stage_prefix": used_stage_prefix,
        "stage_prefix_fallback_used": bool(used_stage_prefix != requested_stage_prefix),
        "requested_offender_threshold": requested_threshold,
        "used_offender_threshold": used_threshold,
        "rate_family": selection["rate_family"],
        "rate_family_column": selected_rate_column,
        "selected_source_rate_column": selection["selected_source_rate_column"],
        "plain_column_fallback_used": bool(requested_threshold is not None and used_threshold is None),
        "source_rate_columns": source_columns,
        "source_count_columns": count_columns,
    }
    return out, metadata
