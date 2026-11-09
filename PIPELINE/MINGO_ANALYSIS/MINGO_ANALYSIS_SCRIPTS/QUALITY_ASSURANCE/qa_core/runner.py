"""Generic step/task runner for QUALITY_ASSURANCE."""

from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path
import math
import re
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .categories import build_column_manifest, manifest_plot_columns, manifest_quality_columns
from .column_rule_table import (
    ColumnRule,
    load_column_rule_table,
    resolve_column_rule,
    rule_to_threshold_mapping,
    split_default_rule,
)
from .common import (
    apply_date_filter,
    deep_merge_dicts,
    deduplicate_metadata_rows_with_report,
    deduplicate_metadata_rows,
    ensure_station_tree,
    get_station_date_range,
    load_yaml_mapping,
    metadata_path,
    normalize_station_name,
    parse_filename_timestamp_series,
    read_csv_if_exists,
    resolve_filter_timestamp,
    resolve_plot_x_axis,
)
from .epoch_quality import (
    build_epoch_reference_table,
    build_epoch_reference_wide_table,
    build_scalar_value_frame,
    evaluate_scalar_frame,
)
from .epochs import load_online_run_dictionary
from .status_reports import (
    apply_file_quality_status,
    build_parameter_status_summary,
    summarize_column_evaluations_by_file,
)

COMPONENT_COLUMN_RE = re.compile(r"^(?P<source>.+)__([0-9]+)$")
REPO_ROOT = Path(__file__).resolve().parents[5]


def _source_column_from_component_name(column_name: str) -> str | None:
    match = COMPONENT_COLUMN_RE.match(str(column_name))
    if match is None:
        return None
    return match.group("source")


def _task_output_root(step_dir: Path, task_id: int) -> Path:
    return step_dir / f"TASK_{task_id}"


def _output_files_dir(base_dir: Path, station_name: str) -> Path:
    path = base_dir / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS" / station_name / "OUTPUTS" / "FILES"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _output_plots_dir(base_dir: Path, station_name: str) -> Path:
    path = base_dir / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS" / station_name / "OUTPUTS" / "PLOTS"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _step_summary_files_dir(step_dir: Path, station_name: str) -> Path:
    path = step_dir / "OUTPUTS" / station_name / "FILES"
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_step_bundle(step_dir: Path, root_config: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Load one step config plus its simple column/plot configs."""
    step_config = deep_merge_dicts(root_config, load_yaml_mapping(step_dir / "config.yaml", required=True))
    category_config = load_yaml_mapping(step_dir / "columns.yaml")
    plot_config = load_yaml_mapping(step_dir / "plots.yaml")
    return step_config, category_config, plot_config


def _threshold_rule_csv_path(step_dir: Path, config: dict[str, Any]) -> Path | None:
    raw_path = str(config.get("threshold_rules_csv", "")).strip()
    if not raw_path:
        return None
    csv_path = Path(raw_path)
    if not csv_path.is_absolute():
        csv_path = step_dir / csv_path
    return csv_path


def _threshold_rule_table(step_dir: Path, config: dict[str, Any]) -> list[ColumnRule]:
    cache_key = "__threshold_rule_table__"
    cached = config.get(cache_key)
    if isinstance(cached, list):
        return cached
    csv_path = _threshold_rule_csv_path(step_dir, config)
    rules = load_column_rule_table(csv_path) if csv_path is not None and csv_path.exists() else []
    config[cache_key] = rules
    return rules


def _resolve_effective_rule(
    rules: list[ColumnRule],
    column_name: str,
    *,
    source_column: str | None = None,
) -> ColumnRule | None:
    if source_column is None:
        source_column = _source_column_from_component_name(column_name)

    direct_rule = resolve_column_rule(column_name, rules) if rules else None
    if source_column is None or source_column == column_name:
        return direct_rule

    source_rule = resolve_column_rule(source_column, rules) if rules else None
    if direct_rule is None:
        return source_rule
    if source_rule is None:
        return direct_rule
    if direct_rule.pattern == "*" and source_rule.pattern != "*":
        return source_rule
    return direct_rule


def _yaml_quality_rule_override(
    config: dict[str, Any],
    evaluation_column: str,
    source_column: str,
) -> dict[str, Any]:
    """Resolve the most specific YAML quality_rules pattern for one observable."""
    raw_rules = config.get("quality_rules")
    if raw_rules is None:
        return {}
    if not isinstance(raw_rules, dict):
        raise ValueError("quality_rules must be a mapping of glob patterns to rules.")

    candidates: list[tuple[tuple[int, int, int, int], dict[str, Any]]] = []
    for row_index, (raw_pattern, raw_rule) in enumerate(raw_rules.items()):
        pattern = str(raw_pattern).strip()
        if not pattern:
            continue
        if not isinstance(raw_rule, dict):
            raise ValueError(f"quality_rules[{pattern!r}] must be a mapping.")
        if not (fnmatch(evaluation_column, pattern) or fnmatch(source_column, pattern)):
            continue
        wildcard_count = sum(pattern.count(token) for token in ("*", "?", "["))
        literal_count = len(pattern.replace("*", "").replace("?", "").replace("[", "").replace("]", ""))
        exact = int(pattern in {evaluation_column, source_column})
        candidates.append(((exact, literal_count, -wildcard_count, row_index), dict(raw_rule)))
    if not candidates:
        return {}
    return max(candidates, key=lambda item: item[0])[1]


def _quality_threshold_config_for_specs(
    *,
    step_dir: Path,
    config: dict[str, Any],
    specs_df: pd.DataFrame,
) -> tuple[dict[str, Any] | None, dict[str, dict[str, Any]] | None]:
    rules = _threshold_rule_table(step_dir, config)
    defaults_cfg = config.get("quality_defaults")
    defaults = dict(defaults_cfg) if isinstance(defaults_cfg, dict) else None

    default_rule, _ = split_default_rule(rules)
    if default_rule is not None:
        default_mapping = rule_to_threshold_mapping(default_rule)
        defaults = deep_merge_dicts(defaults or {}, default_mapping)

    column_rules: dict[str, dict[str, Any]] = {}
    for spec in specs_df.to_dict("records"):
        evaluation_column = str(spec["evaluation_column"])
        source_column = str(spec["source_column"])
        resolved_rule = _resolve_effective_rule(
            rules,
            evaluation_column,
            source_column=source_column,
        )
        csv_mapping = (
            rule_to_threshold_mapping(resolved_rule)
            if resolved_rule is not None else {}
        )
        yaml_mapping = _yaml_quality_rule_override(
            config, evaluation_column, source_column,
        )
        effective_mapping = deep_merge_dicts(csv_mapping, yaml_mapping)
        if effective_mapping:
            column_rules[evaluation_column] = effective_mapping
    return defaults, column_rules or None


def _load_metadata_frame(path: Path) -> pd.DataFrame:
    if path.exists() and path.stat().st_size > 0:
        return pd.read_csv(path, low_memory=False)
    return pd.DataFrame(columns=["filename_base"])


def _prepare_scope_dataframe(station_name: str, config: dict[str, Any], meta_df: pd.DataFrame) -> pd.DataFrame:
    df = deduplicate_metadata_rows(meta_df)
    if df.empty:
        return df

    try:
        timestamps, timestamp_source = resolve_filter_timestamp(df, config)
        df["__timestamp__"] = timestamps
        df["qa_timestamp_source"] = timestamp_source
    except (KeyError, ValueError):
        df["__timestamp__"] = pd.NaT
        df["qa_timestamp_source"] = ""

    date_range = get_station_date_range(config=config, station=station_name)
    if date_range is None:
        df["qa_in_scope"] = df["__timestamp__"].notna()
    else:
        filtered = apply_date_filter(df.loc[df["__timestamp__"].notna()].copy(), date_range)
        df["qa_in_scope"] = df.index.isin(filtered.index)
    return df


def _prepare_analysis_dataframe(station_name: str, config: dict[str, Any], meta_df: pd.DataFrame) -> tuple[pd.DataFrame, str | None]:
    if meta_df.empty:
        return pd.DataFrame(), "empty_metadata"

    scope_df = _prepare_scope_dataframe(station_name=station_name, config=config, meta_df=meta_df)
    if scope_df.empty:
        return pd.DataFrame(), "empty_metadata"

    df = scope_df.loc[scope_df["qa_in_scope"]].copy()
    if df.empty:
        return pd.DataFrame(), "all rows filtered out by date_range"

    x_values, x_label, _ = resolve_plot_x_axis(df, config)
    df["__plot_x__"] = x_values
    df = df.loc[df["__plot_x__"].notna()].copy()
    if df.empty:
        return pd.DataFrame(), "no rows with valid x-axis values"

    sort_key = "__plot_x__" if x_label != "__timestamp__" else "__timestamp__"
    df = df.sort_values(sort_key).reset_index(drop=True)
    return df, None


def _attach_epoch_metadata(repo_root: Path, station_name: str, analyzed_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if analyzed_df.empty or station_name == "MINGO00":
        df = analyzed_df.copy()
        df["epoch_id"] = pd.Series(pd.NA, index=df.index, dtype="string")
        return df, pd.DataFrame()

    try:
        epochs_df = load_online_run_dictionary(repo_root, int(station_name.removeprefix("MINGO")))
    except (FileNotFoundError, ValueError):
        df = analyzed_df.copy()
        df["epoch_id"] = pd.Series(pd.NA, index=df.index, dtype="string")
        return df, pd.DataFrame()

    df = analyzed_df.copy()
    epoch_records: list[str | None] = []
    for timestamp in df["__timestamp__"]:
        match = epochs_df[
            epochs_df["start_timestamp"].notna()
            & (epochs_df["start_timestamp"] <= timestamp)
            & (epochs_df["end_timestamp"].isna() | (timestamp <= epochs_df["end_timestamp"]))
        ]
        epoch_records.append(None if match.empty else str(match.iloc[-1]["epoch_id"]))
    df["epoch_id"] = pd.array(epoch_records, dtype="string")
    return df, epochs_df


def _enrich_reference_table(reference_df: pd.DataFrame, epochs_df: pd.DataFrame, station_name: str) -> pd.DataFrame:
    if reference_df.empty:
        return reference_df

    epoch_columns = [
        column
        for column in (
            "epoch_id",
            "conf_number",
            "start_date",
            "end_date",
            "location",
            "comment",
            "boundary_overlap",
        )
        if column in epochs_df.columns
    ]
    epoch_lookup = epochs_df[epoch_columns].drop_duplicates(subset=["epoch_id"])
    out = reference_df.merge(epoch_lookup, on="epoch_id", how="left")
    out.insert(0, "station_name", station_name)
    return out


def _reference_wide_output_filename(reference_filename: str) -> str:
    reference_path = Path(reference_filename)
    return f"{reference_path.stem}_medians_wide{reference_path.suffix or '.csv'}"


def _cleanup_task_quality_artifacts(task_output_dir: Path, station_name: str, metadata_type: str) -> None:
    files_dir = _output_files_dir(task_output_dir, station_name)
    for path in (
        files_dir / f"{metadata_type}_column_evaluations.csv",
        files_dir / f"{metadata_type}_epoch_references.csv",
        files_dir / _reference_wide_output_filename(f"{metadata_type}_epoch_references.csv"),
    ):
        if path.exists():
            path.unlink()


def _cleanup_task_plot_artifacts(task_output_dir: Path, station_name: str) -> None:
    plots_dir = _output_plots_dir(task_output_dir, station_name)
    for path in plots_dir.iterdir():
        if path.is_file():
            path.unlink()


def _build_pass_dataframe(meta_df: pd.DataFrame, pass_column: str, default_pass: float) -> pd.DataFrame:
    if "filename_base" not in meta_df.columns:
        return pd.DataFrame(columns=["filename_base", pass_column])
    out = pd.DataFrame()
    out["filename_base"] = meta_df["filename_base"].astype("string").fillna("").str.strip()
    out = out[out["filename_base"] != ""].drop_duplicates().reset_index(drop=True)
    out[pass_column] = float(default_pass)
    return out


def _metadata_context_columns(df: pd.DataFrame) -> list[str]:
    return [column for column in ("execution_timestamp", "execution_date") if column in df.columns]


def _attach_metadata_context(frame: pd.DataFrame, metadata_df: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or metadata_df.empty or "filename_base" not in frame.columns or "filename_base" not in metadata_df.columns:
        return frame

    context_columns = _metadata_context_columns(metadata_df)
    if not context_columns:
        return frame

    context_df = metadata_df[["filename_base", *context_columns]].drop_duplicates(subset=["filename_base"])
    out = frame.merge(context_df, on="filename_base", how="left")
    return out


def _write_column_manifest(
    *,
    task_output_dir: Path,
    station_name: str,
    task_id: int,
    metadata_type: str,
    manifest_df: pd.DataFrame,
) -> Path:
    path = _output_files_dir(task_output_dir, station_name) / f"{station_name}_task_{task_id}_{metadata_type}_column_manifest.csv"
    manifest_df.to_csv(path, index=False)
    return path


def _write_overwritten_metadata_report(
    *,
    task_output_dir: Path,
    station_name: str,
    task_id: int,
    metadata_type: str,
    overwritten_df: pd.DataFrame,
) -> Path:
    path = _output_files_dir(task_output_dir, station_name) / f"{station_name}_task_{task_id}_{metadata_type}_overwritten_metadata_rows.csv"
    overwritten_df.to_csv(path, index=False)
    return path


def _first_timestamp(series: pd.Series) -> pd.Timestamp | None:
    parsed = pd.to_datetime(series, errors="coerce")
    parsed = parsed.dropna()
    return None if parsed.empty else parsed.iloc[0]


def _resolve_summary_plot_timestamp(frame: pd.DataFrame, *, fallback_column: str) -> pd.Series:
    if "filename_base" in frame.columns:
        basename_timestamp = parse_filename_timestamp_series(frame["filename_base"])
    else:
        basename_timestamp = pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns]")

    if fallback_column in frame.columns:
        fallback_timestamp = pd.to_datetime(frame[fallback_column], errors="coerce")
    else:
        fallback_timestamp = pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns]")

    return basename_timestamp.where(basename_timestamp.notna(), fallback_timestamp)


def _filter_summary_output_frame(
    frame: pd.DataFrame,
    *,
    station_name: str,
    config: dict[str, Any] | None,
    timestamp_column: str,
) -> pd.DataFrame:
    if frame.empty or config is None or timestamp_column not in frame.columns:
        return frame

    filtered = frame.copy()
    filtered[timestamp_column] = pd.to_datetime(filtered[timestamp_column], errors="coerce")

    date_range = get_station_date_range(config=config, station=station_name)
    if date_range is None:
        return filtered

    filtered["__timestamp__"] = filtered[timestamp_column]
    filtered = filtered.loc[filtered["__timestamp__"].notna()].copy()
    if filtered.empty:
        return filtered.drop(columns="__timestamp__", errors="ignore")

    filtered = apply_date_filter(filtered, date_range)
    return filtered.drop(columns="__timestamp__", errors="ignore").reset_index(drop=True)


def _task_manifest_has_quality(task_output_dir: Path, station_name: str) -> bool | None:
    files_dir = task_output_dir / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS" / station_name / "OUTPUTS" / "FILES"
    manifest_paths = sorted(files_dir.glob("*_column_manifest.csv"))
    if not manifest_paths:
        return None

    quality_found = False
    for manifest_path in manifest_paths:
        manifest_df = read_csv_if_exists(manifest_path)
        if manifest_df.empty or "effective_quality" not in manifest_df.columns:
            continue
        effective_quality = pd.to_numeric(manifest_df["effective_quality"], errors="coerce").fillna(0)
        if (effective_quality > 0).any():
            quality_found = True
            break
    return quality_found


def _unique_preserve(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _resolve_columns(available_columns: list[str], patterns: list[str]) -> list[str]:
    resolved: list[str] = []
    for pattern in patterns:
        pat = str(pattern).strip()
        if not pat:
            continue
        if any(token in pat for token in ("*", "?", "[", "]")):
            matches = [col for col in available_columns if fnmatch(col, pat)]
            if not matches and not pat.endswith("__*"):
                matches = [col for col in available_columns if fnmatch(col, f"{pat}__*")]
            resolved.extend(matches)
        elif pat in available_columns:
            resolved.append(pat)
        else:
            resolved.extend([col for col in available_columns if fnmatch(col, f"{pat}__*")])
    return _unique_preserve(resolved)


def _split_single_star_pattern(pattern: str) -> tuple[str, str] | None:
    if pattern.count("*") != 1:
        return None
    prefix, suffix = pattern.split("*", 1)
    return prefix, suffix


def _resolve_overlay_panels(series_patterns: list[list[str]], available_columns: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    series_maps: list[dict[str, str]] = []
    for patterns in series_patterns:
        mapping: dict[str, str] = {}
        for pattern in patterns:
            pat = str(pattern).strip()
            if not pat:
                continue

            star = _split_single_star_pattern(pat)
            if star is None:
                if pat in available_columns:
                    mapping[pat] = pat
                continue

            prefix, suffix = star
            for col in available_columns:
                if not col.startswith(prefix):
                    continue
                if suffix and not col.endswith(suffix):
                    continue
                middle = col[len(prefix) :]
                if suffix:
                    middle = middle[: -len(suffix)]
                mapping[middle] = col
        series_maps.append(mapping)

    panel_keys = sorted({key for mapping in series_maps for key in mapping})
    panels = [{"title": key, "columns": [mapping.get(key) for mapping in series_maps]} for key in panel_keys]
    consumed = _unique_preserve([column for mapping in series_maps for column in mapping.values()])
    return panels, consumed


def _chunk_columns(columns: list[str], chunk_size: int) -> list[list[str]]:
    if chunk_size <= 0 or len(columns) <= chunk_size:
        return [columns]
    return [columns[idx : idx + chunk_size] for idx in range(0, len(columns), chunk_size)]


def _plot_grid_shape(n_panels: int, ncols: int | None = None, nrows: int | None = None) -> tuple[int, int]:
    if n_panels <= 0:
        return 1, 1
    if nrows and nrows > 0 and ncols and ncols > 0:
        return nrows, ncols
    if ncols and ncols > 0:
        return int(math.ceil(n_panels / ncols)), ncols
    ncols_auto = int(math.ceil(math.sqrt(n_panels)))
    return int(math.ceil(n_panels / ncols_auto)), ncols_auto


def _coerce_shared_axis(value: Any, *, default: bool | str = False) -> bool | str:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if not text:
        return default
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off", "none"}:
        return False
    if text in {"all", "row", "col"}:
        return text
    return default


def _coerce_ylim(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        lower = float(value[0])
        upper = float(value[1])
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(lower) and math.isfinite(upper)) or lower == upper:
        return None
    return (lower, upper) if lower < upper else (upper, lower)


def _quality_bounds_for_plot(
    df: pd.DataFrame,
    quality_evaluations: pd.DataFrame | None,
    evaluation_column: str,
) -> tuple[pd.Series, pd.Series] | None:
    """Align persisted QA bounds to the plotted metadata rows by basename."""
    required = {"filename_base", "evaluation_column", "lower_bound", "upper_bound"}
    if (
        quality_evaluations is None
        or quality_evaluations.empty
        or "filename_base" not in df.columns
        or not required <= set(quality_evaluations.columns)
    ):
        return None
    selected = quality_evaluations.loc[
        quality_evaluations["evaluation_column"].astype(str).eq(evaluation_column),
        ["filename_base", "lower_bound", "upper_bound"],
    ].drop_duplicates(subset="filename_base", keep="last")
    if selected.empty:
        return None
    aligned = df[["filename_base"]].merge(selected, on="filename_base", how="left")
    lower = pd.to_numeric(aligned["lower_bound"], errors="coerce")
    upper = pd.to_numeric(aligned["upper_bound"], errors="coerce")
    if not (lower.notna() & upper.notna()).any():
        return None
    return lower, upper


def _quality_status_for_plot(
    df: pd.DataFrame,
    quality_evaluations: pd.DataFrame | None,
    evaluation_column: str,
) -> pd.Series:
    """Align persisted per-column QA status to plotted metadata rows."""
    required = {"filename_base", "evaluation_column", "status"}
    if (
        quality_evaluations is None
        or quality_evaluations.empty
        or "filename_base" not in df.columns
        or not required <= set(quality_evaluations.columns)
    ):
        return pd.Series("", index=df.index, dtype="object")
    selected = quality_evaluations.loc[
        quality_evaluations["evaluation_column"].astype(str).eq(evaluation_column),
        ["filename_base", "status"],
    ].drop_duplicates(subset="filename_base", keep="last")
    aligned = df[["filename_base"]].merge(selected, on="filename_base", how="left")
    return aligned["status"].fillna("").astype(str).str.strip().str.lower()


def _load_retry_plot_states(station_name: str) -> pd.DataFrame:
    """Load the station active QA retry lifecycle state for plot markers."""
    station_id = int(station_name[-2:])
    path = (
        REPO_ROOT / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS" / station_name
        / "STAGE_0" / "REPROCESSING" / "STEP_0" / "METADATA"
        / f"qa_retry_state_{station_id}.csv"
    )
    if not path.is_file():
        return pd.DataFrame(columns=["basename", "is_active", "admitted_at"])
    frame = read_csv_if_exists(path)
    required = {"basename", "is_active", "admitted_at"}
    if frame.empty or not required <= set(frame.columns):
        return pd.DataFrame(columns=["basename", "is_active", "admitted_at"])
    return frame.loc[
        frame["is_active"].astype(str).str.strip().eq("1"),
        ["basename", "is_active", "admitted_at"],
    ].drop_duplicates(subset="basename", keep="last")


def _retry_phase_for_plot(
    df: pd.DataFrame,
    retry_states: pd.DataFrame | None,
) -> pd.Series:
    """Return queued or in_flight for active QA retry basenames."""
    if (
        retry_states is None
        or retry_states.empty
        or "filename_base" not in df.columns
        or not {"basename", "admitted_at"} <= set(retry_states.columns)
    ):
        return pd.Series("", index=df.index, dtype="object")
    selected = retry_states[["basename", "admitted_at"]].drop_duplicates(
        subset="basename", keep="last"
    )
    aligned = df[["filename_base"]].merge(
        selected, left_on="filename_base", right_on="basename", how="left"
    )
    admitted = aligned["admitted_at"].fillna("").astype(str).str.strip()
    active = aligned["basename"].notna()
    return pd.Series(
        np.where(active & admitted.ne(""), "in_flight", np.where(active, "queued", "")),
        index=df.index,
        dtype="object",
    )


def _draw_quality_band(
    ax: Any,
    x_values: pd.Series,
    bounds: tuple[pd.Series, pd.Series] | None,
    *,
    color: Any,
    label: str,
) -> bool:
    if bounds is None:
        return False
    lower, upper = bounds
    valid = lower.notna() & upper.notna()
    if not valid.any():
        return False
    ax.fill_between(
        x_values, lower, upper, where=valid, step="mid",
        color=color, alpha=0.16, linewidth=0, label=label, zorder=0,
    )
    return True


def _scatter_quality_points(
    ax: Any,
    *,
    df: pd.DataFrame,
    x_values: pd.Series,
    y_values: pd.Series,
    evaluation_column: str,
    label: str,
    marker_size: float,
    quality_evaluations: pd.DataFrame | None,
    marker_labels_used: set[str],
) -> Any:
    """Draw normal, queued-failure, and in-flight-failure point populations."""
    statuses = _quality_status_for_plot(df, quality_evaluations, evaluation_column)
    retry_phase = df.get(
        "__qa_retry_phase__", pd.Series("", index=df.index, dtype="object")
    ).astype(str)
    valid = y_values.notna()
    failed = valid & statuses.eq("fail")
    in_flight = failed & retry_phase.eq("in_flight")
    queued = failed & ~in_flight
    ordinary = valid & ~failed

    points = ax.scatter(
        x_values[ordinary], y_values[ordinary],
        s=marker_size**2, label=label, zorder=2,
    )
    facecolors = points.get_facecolors()
    color = facecolors[0] if len(facecolors) else "tab:blue"
    failure_size = max(marker_size * 2.8, 5.0) ** 2

    if queued.any():
        marker_label = "QA fail: queued"
        ax.scatter(
            x_values[queued], y_values[queued],
            s=failure_size, marker="x", color="red", linewidths=0.9,
            label=marker_label if marker_label not in marker_labels_used else "_nolegend_",
            zorder=4,
        )
        marker_labels_used.add(marker_label)
    if in_flight.any():
        marker_label = "QA retry: in flight"
        ax.scatter(
            x_values[in_flight], y_values[in_flight],
            s=failure_size, marker="D", color="purple", edgecolors="white",
            linewidths=0.35,
            label=marker_label if marker_label not in marker_labels_used else "_nolegend_",
            zorder=5,
        )
        marker_labels_used.add(marker_label)
    return color


def _plot_columns_group(
    *,
    df: pd.DataFrame,
    x_values: pd.Series,
    x_label: str,
    x_is_datetime: bool,
    columns: list[str],
    station_name: str,
    task_id: int,
    metadata_type: str,
    group_name: str,
    out_dir: Path,
    plot_defaults: dict[str, Any],
    quality_evaluations: pd.DataFrame | None = None,
    ncols: int | None = None,
    nrows: int | None = None,
    sharey: bool | str = False,
    ylim: tuple[float, float] | None = None,
) -> Path | None:
    if not columns:
        return None

    nrows_eff, ncols_eff = _plot_grid_shape(len(columns), ncols=ncols, nrows=nrows)
    dpi = int(plot_defaults.get("dpi", 150))
    marker_size = float(plot_defaults.get("marker_size", 2.0))
    image_format = str(plot_defaults.get("format", "png")).strip().lower() or "png"
    fig_width = float(plot_defaults.get("figsize_per_col", 4.2)) * ncols_eff
    fig_height = float(plot_defaults.get("figsize_per_row", 2.8)) * max(nrows_eff, 1)

    fig, axes = plt.subplots(
        nrows=nrows_eff,
        ncols=ncols_eff,
        figsize=(fig_width, fig_height),
        sharex=True,
        sharey=sharey,
    )
    axes_flat = np.ravel(axes)

    for idx, col in enumerate(columns):
        ax = axes_flat[idx]
        y = pd.to_numeric(df[col], errors="coerce")
        band_drawn = False
        if y.notna().any():
            color = _scatter_quality_points(
                ax, df=df, x_values=x_values, y_values=y,
                evaluation_column=col, label=col, marker_size=marker_size,
                quality_evaluations=quality_evaluations, marker_labels_used=set(),
            )
            band_drawn = _draw_quality_band(
                ax, x_values,
                _quality_bounds_for_plot(df, quality_evaluations, col),
                color=color, label="passing range",
            )
        else:
            ax.text(0.5, 0.5, "no data", ha="center", va="center", color="gray", fontsize=9)
        ax.set_title(col, fontsize=8)
        ax.grid(True, alpha=0.25)
        if band_drawn:
            ax.legend(fontsize=7, loc="best")
        if ylim is not None:
            ax.set_ylim(*ylim)

    for idx in range(len(columns), len(axes_flat)):
        axes_flat[idx].axis("off")

    fig.suptitle(f"TASK_{task_id} {station_name} {metadata_type} - {group_name} (x={x_label})", fontsize=11)
    if x_is_datetime:
        fig.autofmt_xdate(rotation=30)
    fig.tight_layout(rect=(0, 0, 1, 0.96))

    out_path = out_dir / f"{station_name}_task_{task_id}_{metadata_type}_{group_name}.{image_format}"
    fig.savefig(out_path, dpi=dpi)
    plt.close(fig)
    return out_path


def _plot_overlay_group(
    *,
    df: pd.DataFrame,
    x_values: pd.Series,
    x_label: str,
    x_is_datetime: bool,
    panels: list[dict[str, Any]],
    series_labels: list[str],
    station_name: str,
    task_id: int,
    metadata_type: str,
    group_name: str,
    out_dir: Path,
    plot_defaults: dict[str, Any],
    quality_evaluations: pd.DataFrame | None = None,
    ncols: int | None = None,
    nrows: int | None = None,
    sharey: bool | str = False,
    ylim: tuple[float, float] | None = None,
) -> Path | None:
    if not panels:
        return None

    nrows_eff, ncols_eff = _plot_grid_shape(len(panels), ncols=ncols, nrows=nrows)
    dpi = int(plot_defaults.get("dpi", 150))
    marker_size = float(plot_defaults.get("marker_size", 2.0))
    image_format = str(plot_defaults.get("format", "png")).strip().lower() or "png"
    fig_width = float(plot_defaults.get("figsize_per_col", 4.2)) * ncols_eff
    fig_height = float(plot_defaults.get("figsize_per_row", 2.8)) * max(nrows_eff, 1)

    fig, axes = plt.subplots(
        nrows=nrows_eff,
        ncols=ncols_eff,
        figsize=(fig_width, fig_height),
        sharex=True,
        sharey=sharey,
    )
    axes_flat = np.ravel(axes)

    for idx, panel in enumerate(panels):
        ax = axes_flat[idx]
        title = str(panel.get("title", f"panel_{idx + 1}"))
        columns = panel.get("columns", [])
        has_data = False
        band_drawn = False
        plotted_labels: list[str] = []
        marker_labels_used: set[str] = set()
        for series_idx, col in enumerate(columns):
            label = series_labels[series_idx] if series_idx < len(series_labels) else f"series_{series_idx + 1}"
            if not col or col not in df.columns:
                continue
            y = pd.to_numeric(df[col], errors="coerce")
            if y.notna().any():
                color = _scatter_quality_points(
                    ax, df=df, x_values=x_values, y_values=y,
                    evaluation_column=str(col), label=label, marker_size=marker_size,
                    quality_evaluations=quality_evaluations,
                    marker_labels_used=marker_labels_used,
                )
                band_drawn = _draw_quality_band(
                    ax, x_values,
                    _quality_bounds_for_plot(df, quality_evaluations, str(col)),
                    color=color, label=f"{label} passing range",
                ) or band_drawn
                has_data = True
                plotted_labels.append(label)
        if not has_data:
            ax.text(0.5, 0.5, "no data", ha="center", va="center", color="gray", fontsize=9)
        ax.set_title(title, fontsize=8)
        ax.grid(True, alpha=0.25)
        if len(plotted_labels) > 1 or band_drawn:
            ax.legend(fontsize=7, loc="best")
        if ylim is not None:
            ax.set_ylim(*ylim)

    for idx in range(len(panels), len(axes_flat)):
        axes_flat[idx].axis("off")

    fig.suptitle(f"TASK_{task_id} {station_name} {metadata_type} - {group_name} (x={x_label})", fontsize=11)
    if x_is_datetime:
        fig.autofmt_xdate(rotation=30)
    fig.tight_layout(rect=(0, 0, 1, 0.96))

    out_path = out_dir / f"{station_name}_task_{task_id}_{metadata_type}_{group_name}.{image_format}"
    fig.savefig(out_path, dpi=dpi)
    plt.close(fig)
    return out_path


def _special_plot_groups(plot_config: dict[str, Any], task_id: int) -> list[dict[str, Any]]:
    groups = plot_config.get("special", [])
    if not isinstance(groups, list):
        return []
    out: list[dict[str, Any]] = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        tasks = group.get("tasks")
        if isinstance(tasks, list) and task_id not in {int(value) for value in tasks}:
            continue
        out.append(group)
    return out


def _resolve_explicit_panels(
    panels_cfg: Any,
    available_columns: list[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    if not isinstance(panels_cfg, list):
        return [], []

    panels: list[dict[str, Any]] = []
    consumed: list[str] = []
    for idx, panel_cfg in enumerate(panels_cfg):
        if not isinstance(panel_cfg, dict):
            continue
        title = str(panel_cfg.get("title", f"panel_{idx + 1}")).strip() or f"panel_{idx + 1}"
        raw_columns = panel_cfg.get("columns", [])
        if isinstance(raw_columns, str):
            panel_columns_raw = [raw_columns]
        elif isinstance(raw_columns, list):
            panel_columns_raw = raw_columns
        else:
            panel_columns_raw = []

        panel_columns: list[str | None] = []
        for value in panel_columns_raw:
            if value is None:
                panel_columns.append(None)
                continue
            column_name = str(value).strip()
            if not column_name:
                panel_columns.append(None)
                continue
            panel_columns.append(column_name)
            if column_name in available_columns:
                consumed.append(column_name)

        if not panel_columns:
            continue
        panels.append({"title": title, "columns": panel_columns})

    return panels, _unique_preserve(consumed)


def _generate_station_plots(
    *,
    task_output_dir: Path,
    station_name: str,
    task_id: int,
    metadata_type: str,
    analyzed_df: pd.DataFrame,
    plot_columns: list[str],
    config: dict[str, Any],
    plot_config: dict[str, Any],
    quality_evaluations: pd.DataFrame | None = None,
) -> list[Path]:
    if analyzed_df.empty or not plot_columns:
        return []

    df = analyzed_df.copy()
    x_values, x_label, x_is_datetime = resolve_plot_x_axis(df, config)
    df["__plot_x__"] = x_values
    sort_key = "__plot_x__" if x_label != "__timestamp__" else "__timestamp__"
    df = df.sort_values(sort_key).reset_index(drop=True)
    x_values = df["__plot_x__"]
    df["__qa_retry_phase__"] = _retry_phase_for_plot(
        df, _load_retry_plot_states(station_name)
    )

    plots_dir = _output_plots_dir(task_output_dir, station_name)
    plot_defaults = deep_merge_dicts(
        config.get("plots", {}) if isinstance(config.get("plots"), dict) else {},
        plot_config.get("default", {}) if isinstance(plot_config.get("default"), dict) else {},
    )
    image_format = str(plot_defaults.get("format", "png")).strip().lower() or "png"

    available_plot_columns = [col for col in df.columns if col in set(plot_columns)]
    consumed: list[str] = []
    created: list[Path] = []

    for group in _special_plot_groups(plot_config, task_id):
        mode = str(group.get("mode", "columns")).strip().lower() or "columns"
        name = str(group.get("name", f"group_{len(created) + 1}")).strip() or f"group_{len(created) + 1}"
        ncols = int(group["ncols"]) if "ncols" in group else None
        nrows = int(group["nrows"]) if "nrows" in group else None
        sharey = _coerce_shared_axis(group.get("sharey", plot_defaults.get("sharey", False)))
        ylim = _coerce_ylim(group.get("ylim", plot_defaults.get("ylim")))
        if mode == "overlay":
            series_cfg = group.get("series", [])
            if not isinstance(series_cfg, list) or not series_cfg:
                continue
            series_patterns: list[list[str]] = []
            labels: list[str] = []
            for series in series_cfg:
                if not isinstance(series, dict):
                    continue
                raw_patterns = series.get("columns", [])
                if isinstance(raw_patterns, str):
                    patterns = [raw_patterns]
                elif isinstance(raw_patterns, list):
                    patterns = [str(value).strip() for value in raw_patterns if str(value).strip()]
                else:
                    patterns = []
                if not patterns:
                    continue
                series_patterns.append(patterns)
                labels.append(str(series.get("label", f"series_{len(labels) + 1}")).strip() or f"series_{len(labels) + 1}")
            if not series_patterns:
                continue
            panels, used_columns = _resolve_overlay_panels(series_patterns, available_plot_columns)
            out_path = _plot_overlay_group(
                df=df,
                x_values=x_values,
                x_label=x_label,
                x_is_datetime=x_is_datetime,
                panels=panels,
                series_labels=labels,
                station_name=station_name,
                task_id=task_id,
                metadata_type=metadata_type,
                group_name=name,
                out_dir=plots_dir,
                plot_defaults=plot_defaults,
                quality_evaluations=quality_evaluations,
                ncols=ncols,
                nrows=nrows,
                sharey=sharey,
                ylim=ylim,
            )
            consumed.extend(used_columns)
        elif mode == "panels":
            raw_labels = group.get("series_labels", group.get("labels", []))
            if isinstance(raw_labels, str):
                labels = [raw_labels]
            elif isinstance(raw_labels, list):
                labels = [str(value).strip() for value in raw_labels if str(value).strip()]
            else:
                labels = []
            panels, used_columns = _resolve_explicit_panels(
                group.get("panels", []),
                available_plot_columns,
            )
            if not panels:
                continue
            out_path = _plot_overlay_group(
                df=df,
                x_values=x_values,
                x_label=x_label,
                x_is_datetime=x_is_datetime,
                panels=panels,
                series_labels=labels,
                station_name=station_name,
                task_id=task_id,
                metadata_type=metadata_type,
                group_name=name,
                out_dir=plots_dir,
                plot_defaults=plot_defaults,
                quality_evaluations=quality_evaluations,
                ncols=ncols,
                nrows=nrows,
                sharey=sharey,
                ylim=ylim,
            )
            consumed.extend(used_columns)
        else:
            raw_columns = group.get("columns", [])
            if isinstance(raw_columns, str):
                patterns = [raw_columns]
            elif isinstance(raw_columns, list):
                patterns = [str(value).strip() for value in raw_columns if str(value).strip()]
            else:
                patterns = []
            columns = [col for col in _resolve_columns(available_plot_columns, patterns) if col in available_plot_columns]
            if not columns:
                continue
            out_path = _plot_columns_group(
                df=df,
                x_values=x_values,
                x_label=x_label,
                x_is_datetime=x_is_datetime,
                columns=columns,
                station_name=station_name,
                task_id=task_id,
                metadata_type=metadata_type,
                group_name=name,
                out_dir=plots_dir,
                plot_defaults=plot_defaults,
                quality_evaluations=quality_evaluations,
                ncols=ncols,
                nrows=nrows,
                sharey=sharey,
                ylim=ylim,
            )
            consumed.extend(columns)
        if out_path is not None:
            created.append(out_path)

    max_columns = int(plot_defaults.get("default_max_columns_per_plot", 12))
    default_ncols = int(plot_defaults.get("default_ncols", 4))
    default_sharey = _coerce_shared_axis(plot_defaults.get("sharey", False))
    default_ylim = _coerce_ylim(plot_defaults.get("ylim"))
    leftover_columns = [col for col in plot_columns if col not in set(consumed) and col in df.columns]
    for chunk_index, chunk in enumerate(_chunk_columns(leftover_columns, max_columns), start=1):
        if not chunk:
            continue
        out_path = _plot_columns_group(
            df=df,
            x_values=x_values,
            x_label=x_label,
            x_is_datetime=x_is_datetime,
            columns=chunk,
            station_name=station_name,
            task_id=task_id,
            metadata_type=metadata_type,
            group_name=f"default_{chunk_index}",
            out_dir=plots_dir,
            plot_defaults=plot_defaults,
            quality_evaluations=quality_evaluations,
            ncols=default_ncols,
            sharey=default_sharey,
            ylim=default_ylim,
        )
        if out_path is not None:
            created.append(out_path)

    return created


def _write_epoch_reference_table(
    *,
    task_output_dir: Path,
    step_dir: Path,
    station_name: str,
    metadata_type: str,
    analyzed_df: pd.DataFrame,
    epochs_df: pd.DataFrame,
    quality_columns: list[str],
    config: dict[str, Any],
) -> tuple[pd.DataFrame, Path | None]:
    if analyzed_df.empty or epochs_df.empty or not quality_columns:
        return pd.DataFrame(), None

    value_frame, specs_df = build_scalar_value_frame(analyzed_df, quality_columns)
    defaults, column_rules = _quality_threshold_config_for_specs(
        step_dir=step_dir,
        config=config,
        specs_df=specs_df,
    )
    reference_df = build_epoch_reference_table(
        value_frame,
        specs_df,
        analyzed_df["epoch_id"],
        defaults=defaults,
        column_rules=column_rules,
    )
    if reference_df.empty:
        return pd.DataFrame(), None

    reference_df = _enrich_reference_table(reference_df, epochs_df, station_name)
    output_filename = f"{metadata_type}_epoch_references.csv"
    out_path = _output_files_dir(task_output_dir, station_name) / output_filename
    reference_df.to_csv(out_path, index=False)

    reference_wide_df = build_epoch_reference_wide_table(reference_df, value_column="center_median")
    if not reference_wide_df.empty:
        wide_output_path = _output_files_dir(task_output_dir, station_name) / _reference_wide_output_filename(output_filename)
        reference_wide_df.to_csv(wide_output_path, index=False)
    return reference_df, out_path


def _build_quality_pass_dataframe(
    *,
    task_output_dir: Path,
    step_dir: Path,
    station_name: str,
    metadata_type: str,
    scope_df: pd.DataFrame,
    analyzed_df: pd.DataFrame,
    reference_df: pd.DataFrame,
    quality_columns: list[str],
    config: dict[str, Any],
    pass_column: str,
) -> tuple[pd.DataFrame, Path | None, pd.DataFrame]:
    default_pass = float(config.get("pass_default_value", 1.0))
    if scope_df.empty:
        return pd.DataFrame(columns=["filename_base", pass_column]), None, pd.DataFrame()

    if not quality_columns:
        return (
            _build_pass_dataframe(scope_df, pass_column, default_pass),
            None,
            pd.DataFrame(),
        )

    file_df = scope_df[["filename_base", "__timestamp__", "qa_timestamp_source", "qa_in_scope"]].copy()
    file_df.rename(columns={"__timestamp__": "qa_timestamp"}, inplace=True)
    file_df = _attach_metadata_context(file_df, scope_df)
    file_df["epoch_id"] = pd.Series(pd.NA, index=file_df.index, dtype="string")
    file_df["conf_number"] = pd.Series(pd.NA, index=file_df.index, dtype="Int64")

    if not analyzed_df.empty and "epoch_id" in analyzed_df.columns:
        file_epoch_df = analyzed_df[["filename_base", "epoch_id"]].drop_duplicates(subset=["filename_base"])
        if not reference_df.empty and {"epoch_id", "conf_number"} <= set(reference_df.columns):
            epoch_lookup = reference_df[["epoch_id", "conf_number"]].drop_duplicates(subset=["epoch_id"])
            file_epoch_df = file_epoch_df.merge(epoch_lookup, on="epoch_id", how="left")
        else:
            file_epoch_df["conf_number"] = pd.Series(pd.NA, index=file_epoch_df.index, dtype="Int64")
        file_df = file_df.merge(file_epoch_df, on="filename_base", how="left", suffixes=("", "_eval"))
        file_df["epoch_id"] = file_df["epoch_id_eval"].combine_first(file_df["epoch_id"])
        merged_conf_number = pd.to_numeric(file_df["conf_number_eval"], errors="coerce").astype("Float64")
        base_conf_number = pd.to_numeric(file_df["conf_number"], errors="coerce").astype("Float64")
        file_df["conf_number"] = merged_conf_number.fillna(base_conf_number).astype("Int64")
        file_df = file_df.drop(columns=["epoch_id_eval", "conf_number_eval"])

    column_eval_df = pd.DataFrame()
    if not analyzed_df.empty and not reference_df.empty:
        value_frame, specs_df = build_scalar_value_frame(analyzed_df, quality_columns)
        defaults, column_rules = _quality_threshold_config_for_specs(
            step_dir=step_dir,
            config=config,
            specs_df=specs_df,
        )
        column_eval_df = evaluate_scalar_frame(
            analyzed_df,
            value_frame,
            reference_df,
            defaults=defaults,
            column_rules=column_rules,
        )
        column_eval_df = _attach_metadata_context(column_eval_df, analyzed_df)

    file_summary_df = summarize_column_evaluations_by_file(column_eval_df)
    if not file_summary_df.empty:
        file_df = file_df.merge(file_summary_df, on="filename_base", how="left")
    file_df = apply_file_quality_status(file_df, pass_column=pass_column)

    out_path = None
    if not column_eval_df.empty:
        out_path = _output_files_dir(task_output_dir, station_name) / f"{metadata_type}_column_evaluations.csv"
        column_eval_df.to_csv(out_path, index=False)

    ordered_columns = [
        "filename_base",
        pass_column,
        "qa_status",
        "qa_timestamp",
        "execution_timestamp",
        "execution_date",
        "qa_timestamp_source",
        "qa_in_scope",
        "epoch_id",
        "conf_number",
        "qa_evaluated_columns",
        "qa_passed_columns",
        "qa_failed_columns",
        "qa_warning_columns",
        "qa_pass_fraction",
        "qa_failed_observables",
        "qa_warning_reasons",
    ]
    available_columns = [column for column in ordered_columns if column in file_df.columns]
    return file_df[available_columns].copy(), out_path, column_eval_df


def _collect_step_outputs(
    step_dir: Path,
    display_name: str,
    station_name: str,
    config: dict[str, Any] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    pass_paths = sorted(step_dir.glob(f"TASK_*/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/{station_name}/OUTPUTS/FILES/*_pass.csv"))
    eval_paths = sorted(step_dir.glob(f"TASK_*/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/{station_name}/OUTPUTS/FILES/*_column_evaluations.csv"))

    pass_frames: list[pd.DataFrame] = []
    for path in pass_paths:
        task_id = int(path.parents[5].name.removeprefix("TASK_"))
        frame = read_csv_if_exists(path)
        if frame.empty:
            continue
        frame["task_id"] = task_id
        frame["step_name"] = step_dir.name
        frame["step_display_name"] = display_name
        pass_frames.append(frame)

    eval_frames: list[pd.DataFrame] = []
    for path in eval_paths:
        task_id = int(path.parents[5].name.removeprefix("TASK_"))
        manifest_has_quality = _task_manifest_has_quality(path.parents[5], station_name)
        if manifest_has_quality is False:
            continue
        frame = read_csv_if_exists(path)
        if frame.empty:
            continue
        frame["task_id"] = task_id
        frame["step_name"] = step_dir.name
        frame["step_display_name"] = display_name
        eval_frames.append(frame)

    pass_df = pd.concat(pass_frames, ignore_index=True) if pass_frames else pd.DataFrame()
    eval_df = pd.concat(eval_frames, ignore_index=True) if eval_frames else pd.DataFrame()
    if pass_df.empty:
        return pd.DataFrame(), pd.DataFrame()

    if "qa_timestamp" not in pass_df.columns:
        pass_df["qa_timestamp"] = parse_filename_timestamp_series(pass_df["filename_base"])
    else:
        pass_df["qa_timestamp"] = pd.to_datetime(pass_df["qa_timestamp"], errors="coerce")
    pass_df["plot_timestamp"] = _resolve_summary_plot_timestamp(pass_df, fallback_column="qa_timestamp")
    pass_df = _filter_summary_output_frame(
        pass_df,
        station_name=station_name,
        config=config,
        timestamp_column="plot_timestamp",
    )
    if pass_df.empty:
        return pd.DataFrame(), pd.DataFrame()

    if not eval_df.empty:
        eval_df = eval_df.merge(
            pass_df[["filename_base", "task_id", "qa_timestamp", "plot_timestamp"]].drop_duplicates(
                subset=["filename_base", "task_id"]
            ),
            on=["filename_base", "task_id"],
            how="left",
        )
        eval_df = _filter_summary_output_frame(
            eval_df,
            station_name=station_name,
            config=config,
            timestamp_column="plot_timestamp",
        )

    summary_base = (
        pass_df.groupby("filename_base", dropna=False)
        .agg(
            qa_timestamp=("qa_timestamp", _first_timestamp),
            plot_timestamp=("plot_timestamp", _first_timestamp),
            qa_status_source=("qa_status", lambda values: ";".join(sorted(set(values.astype(str))))) if "qa_status" in pass_df.columns else ("task_id", lambda values: ""),
            qa_status_task_count=("task_id", "nunique"),
        )
        .reset_index()
    )

    if not eval_df.empty:
        labeled_eval_df = eval_df.copy()
        labeled_eval_df["failed_label"] = labeled_eval_df["task_id"].map(lambda value: f"TASK_{int(value)}") + "::" + labeled_eval_df["evaluation_column"].astype(str)
        step_agg = summarize_column_evaluations_by_file(
            labeled_eval_df,
            observable_column="failed_label",
        )
        summary_df = summary_base.merge(step_agg, on="filename_base", how="left")
    else:
        summary_df = summary_base.copy()
        summary_df["qa_evaluated_columns"] = 0
        summary_df["qa_passed_columns"] = 0
        summary_df["qa_failed_columns"] = 0
        summary_df["qa_warning_columns"] = 0
        summary_df["qa_failed_observables"] = ""
        summary_df["qa_warning_reasons"] = ""

    for column_name in (
        "qa_evaluated_columns",
        "qa_passed_columns",
        "qa_failed_columns",
        "qa_warning_columns",
    ):
        summary_df[column_name] = pd.to_numeric(summary_df[column_name], errors="coerce").fillna(0).astype(int)

    summary_df["qa_pass_fraction"] = pd.Series(pd.NA, index=summary_df.index, dtype="Float64")
    valid_mask = summary_df["qa_evaluated_columns"] > 0
    summary_df.loc[valid_mask, "qa_pass_fraction"] = (
        summary_df.loc[valid_mask, "qa_passed_columns"] / summary_df.loc[valid_mask, "qa_evaluated_columns"]
    ).astype(float)

    def _step_status(row: pd.Series) -> str:
        source_tokens = set(str(row.get("qa_status_source", "")).split(";"))
        source_tokens.discard("")
        if row.get("qa_failed_columns", 0) > 0 or "fail" in source_tokens:
            return "fail"
        if row.get("qa_warning_columns", 0) > 0 or "warn" in source_tokens:
            return "warn"
        if "no_epoch_match" in source_tokens and row.get("qa_evaluated_columns", 0) == 0:
            return "no_epoch_match"
        if row.get("qa_evaluated_columns", 0) > 0 and row.get("qa_failed_columns", 0) == 0:
            return "pass"
        if source_tokens == {"out_of_scope"}:
            return "out_of_scope"
        if source_tokens == {"invalid_timestamp"}:
            return "invalid_timestamp"
        return "not_evaluated"

    summary_df["qa_status"] = summary_df.apply(_step_status, axis=1)
    summary_df["step_name"] = step_dir.name
    summary_df["step_display_name"] = display_name
    summary_df = summary_df.sort_values("plot_timestamp", na_position="last").reset_index(drop=True)
    return summary_df, eval_df


def _write_step_outputs(step_dir: Path, display_name: str, station_name: str, summary_df: pd.DataFrame, eval_df: pd.DataFrame) -> None:
    files_dir = _step_summary_files_dir(step_dir, station_name)
    summary_df.to_csv(files_dir / f"{station_name}_{display_name}_step_summary.csv", index=False)

    column_status_path = files_dir / f"{station_name}_{display_name}_column_status.csv"
    parameter_summary_path = files_dir / f"{station_name}_{display_name}_parameter_summary.csv"
    if eval_df.empty:
        if column_status_path.exists():
            column_status_path.unlink()
        if parameter_summary_path.exists():
            parameter_summary_path.unlink()
        return

    eval_df.to_csv(column_status_path, index=False)
    parameter_summary_df = build_parameter_status_summary(
        eval_df,
        group_by=["task_id", "source_column"],
        timestamp_column="plot_timestamp",
    )
    if not parameter_summary_df.empty:
        if {"task_id", "source_column"} <= set(parameter_summary_df.columns):
            parameter_summary_df["parameter_label"] = (
                parameter_summary_df["task_id"].map(lambda value: f"TASK_{int(value)}")
                + "::"
                + parameter_summary_df["source_column"].astype(str)
            )
        parameter_summary_df.to_csv(parameter_summary_path, index=False)
    elif parameter_summary_path.exists():
        parameter_summary_path.unlink()


def run_step(
    step_dir: Path,
    *,
    root_config: dict[str, Any],
    stations_override: list[str] | None = None,
    generate_plots: bool = True,
    quality_plots_only: bool = False,
) -> int:
    """Run one configured QA step across all configured stations/tasks."""
    config, category_config, plot_config = load_step_bundle(step_dir, root_config)
    display_name = str(config.get("display_name", step_dir.name)).strip() or step_dir.name
    task_ids = [int(value) for value in config.get("task_ids", [])]
    metadata_suffix = str(config.get("metadata_suffix", "")).strip()
    metadata_type = str(config.get("metadata_type", metadata_suffix)).strip() or metadata_suffix
    pass_template = str(config.get("pass_column_template", f"task_{{task_id}}_{metadata_type}_pass")).strip()
    stations = stations_override or [normalize_station_name(value) for value in config.get("stations", [])]
    common_ignore = [str(value).strip() for value in config.get("ignore_patterns_common", []) if str(value).strip()]

    if not task_ids:
        raise ValueError(f"{step_dir} is missing non-empty 'task_ids'.")
    if not metadata_suffix:
        raise ValueError(f"{step_dir} is missing 'metadata_suffix'.")
    if not stations:
        raise ValueError(f"{step_dir} is missing non-empty 'stations'.")

    repo_root = step_dir.parents[5]

    total_plots = 0
    total_references = 0
    total_quality_tables = 0

    for task_id in task_ids:
        task_output_dir = _task_output_root(step_dir, task_id)
        ensure_station_tree(task_output_dir, stations)
        metadata_filename = f"task_{task_id}_metadata_{metadata_suffix}.csv"
        pass_column = pass_template.format(task_id=task_id, metadata_type=metadata_type)

        for station_name in stations:
            meta_path = metadata_path(repo_root, station_name, task_id, metadata_filename)
            raw_meta_df = _load_metadata_frame(meta_path)
            meta_df, overwritten_df = deduplicate_metadata_rows_with_report(raw_meta_df)
            overwritten_path = _write_overwritten_metadata_report(
                task_output_dir=task_output_dir,
                station_name=station_name,
                task_id=task_id,
                metadata_type=metadata_type,
                overwritten_df=overwritten_df,
            )
            manifest_df = build_column_manifest(
                meta_df,
                category_config,
                common_ignore_patterns=common_ignore,
            )
            _write_column_manifest(
                task_output_dir=task_output_dir,
                station_name=station_name,
                task_id=task_id,
                metadata_type=metadata_type,
                manifest_df=manifest_df,
            )

            scope_df = _prepare_scope_dataframe(station_name=station_name, config=config, meta_df=meta_df)
            analyzed_df, analysis_reason = _prepare_analysis_dataframe(
                station_name=station_name,
                config=config,
                meta_df=meta_df,
            )
            analyzed_df, epochs_df = _attach_epoch_metadata(repo_root, station_name, analyzed_df)

            plot_columns = manifest_plot_columns(
                manifest_df, quality_and_plot_only=quality_plots_only,
            )
            quality_columns = manifest_quality_columns(manifest_df)
            _cleanup_task_quality_artifacts(task_output_dir, station_name, metadata_type)
            _cleanup_task_plot_artifacts(task_output_dir, station_name)

            reference_df, reference_path = _write_epoch_reference_table(
                task_output_dir=task_output_dir,
                step_dir=step_dir,
                station_name=station_name,
                metadata_type=metadata_type,
                analyzed_df=analyzed_df,
                epochs_df=epochs_df,
                quality_columns=quality_columns,
                config=config,
            )
            pass_df, quality_eval_path, column_eval_df = _build_quality_pass_dataframe(
                task_output_dir=task_output_dir,
                step_dir=step_dir,
                station_name=station_name,
                metadata_type=metadata_type,
                scope_df=scope_df,
                analyzed_df=analyzed_df,
                reference_df=reference_df,
                quality_columns=quality_columns,
                config=config,
                pass_column=pass_column,
            )

            files_dir = _output_files_dir(task_output_dir, station_name)
            pass_path = files_dir / f"{station_name}_task_{task_id}_{metadata_type}_pass.csv"
            pass_df.to_csv(pass_path, index=False)

            if generate_plots:
                created_plots = _generate_station_plots(
                    task_output_dir=task_output_dir,
                    station_name=station_name,
                    task_id=task_id,
                    metadata_type=metadata_type,
                    analyzed_df=analyzed_df,
                    plot_columns=plot_columns,
                    config=config,
                    plot_config=plot_config,
                    quality_evaluations=column_eval_df,
                )
            else:
                created_plots = []

            total_plots += len(created_plots)
            if reference_path is not None:
                total_references += 1
            if quality_eval_path is not None:
                total_quality_tables += 1

            overwritten_count = len(overwritten_df)
            if created_plots or reference_path is not None or quality_eval_path is not None or overwritten_count:
                print(
                    f"{step_dir.name} TASK_{task_id} {station_name}: plots={len(created_plots)} "
                    f"epoch_ref={'yes' if reference_path is not None else 'no'} "
                    f"quality={'yes' if quality_eval_path is not None else 'no'} "
                    f"overwritten_rows={overwritten_count} "
                    f"overwritten_report={overwritten_path.name}"
                )
            elif analysis_reason is not None:
                print(f"{step_dir.name} TASK_{task_id} {station_name}: {analysis_reason}.")

    for station_name in stations:
        summary_df, eval_df = _collect_step_outputs(step_dir, display_name, station_name, config=config)
        if summary_df.empty:
            continue
        _write_step_outputs(step_dir, display_name, station_name, summary_df, eval_df)

    print(
        f"{step_dir.name} complete: tasks={len(task_ids)} stations={len(stations)} "
        f"plots={total_plots} plot_scope={'quality_and_plot' if quality_plots_only else 'all_plottable'} "
        f"epoch_references={total_references} quality_tables={total_quality_tables}"
    )
    return 0


def rebuild_step_summaries(
    step_dir: Path,
    *,
    root_config: dict[str, Any],
    stations_override: list[str] | None = None,
) -> None:
    """Rebuild step-level summary CSVs from existing task outputs only."""
    config, _, _ = load_step_bundle(step_dir, root_config)
    display_name = str(config.get("display_name", step_dir.name)).strip() or step_dir.name
    stations = stations_override or [normalize_station_name(value) for value in config.get("stations", [])]
    for station_name in stations:
        summary_df, eval_df = _collect_step_outputs(step_dir, display_name, station_name, config=config)
        if summary_df.empty:
            continue
        _write_step_outputs(step_dir, display_name, station_name, summary_df, eval_df)
