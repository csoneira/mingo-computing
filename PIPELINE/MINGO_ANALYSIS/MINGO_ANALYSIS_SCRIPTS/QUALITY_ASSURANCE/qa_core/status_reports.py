"""Reusable reporting helpers for QUALITY_ASSURANCE status outputs."""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

EVALUATED_STATUSES = {"pass", "fail"}


def _join_unique(values: pd.Series, *, limit: int | None = None) -> str:
    tokens = sorted(
        {
            str(value).strip()
            for value in values
            if pd.notna(value) and str(value).strip()
        }
    )
    if limit is not None and len(tokens) > limit:
        kept = tokens[:limit]
        kept.append(f"+{len(tokens) - limit}_more")
        return ";".join(kept)
    return ";".join(tokens)


def _empty_file_summary(filename_column: str) -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            filename_column,
            "qa_evaluated_columns",
            "qa_passed_columns",
            "qa_failed_columns",
            "qa_warning_columns",
            "qa_failed_observables",
            "qa_warning_reasons",
        ]
    )


def _with_status_flags(df: pd.DataFrame, *, status_column: str) -> pd.DataFrame:
    working = df.copy()
    status = working[status_column].astype("string").fillna("")
    working["_is_evaluated"] = status.isin(EVALUATED_STATUSES).astype(int)
    working["_is_pass"] = status.eq("pass").astype(int)
    working["_is_fail"] = status.eq("fail").astype(int)
    working["_is_warning"] = (~status.isin(EVALUATED_STATUSES)).astype(int)
    return working


def summarize_column_evaluations_by_file(
    df: pd.DataFrame,
    *,
    filename_column: str = "filename_base",
    status_column: str = "status",
    observable_column: str = "evaluation_column",
    reason_column: str = "reason",
) -> pd.DataFrame:
    """Aggregate column-evaluation rows into one QA summary per file."""
    if df.empty or filename_column not in df.columns or status_column not in df.columns:
        return _empty_file_summary(filename_column)

    use_columns = [filename_column, status_column]
    if observable_column in df.columns:
        use_columns.append(observable_column)
    if reason_column in df.columns:
        use_columns.append(reason_column)

    working = _with_status_flags(df[use_columns], status_column=status_column)
    summary_df = (
        working.groupby(filename_column, dropna=False)
        .agg(
            qa_evaluated_columns=("_is_evaluated", "sum"),
            qa_passed_columns=("_is_pass", "sum"),
            qa_failed_columns=("_is_fail", "sum"),
            qa_warning_columns=("_is_warning", "sum"),
        )
        .reset_index()
    )

    if observable_column in working.columns:
        failed_observables = (
            working.loc[working["_is_fail"] == 1, [filename_column, observable_column]]
            .groupby(filename_column)[observable_column]
            .apply(_join_unique)
            .rename("qa_failed_observables")
        )
        summary_df = summary_df.merge(failed_observables.reset_index(), on=filename_column, how="left")
    else:
        summary_df["qa_failed_observables"] = ""

    if reason_column in working.columns:
        warning_reasons = (
            working.loc[working[status_column].astype("string").fillna("").ne("pass"), [filename_column, reason_column]]
            .groupby(filename_column)[reason_column]
            .apply(_join_unique)
            .rename("qa_warning_reasons")
        )
        summary_df = summary_df.merge(warning_reasons.reset_index(), on=filename_column, how="left")
    else:
        summary_df["qa_warning_reasons"] = ""

    for column_name in (
        "qa_evaluated_columns",
        "qa_passed_columns",
        "qa_failed_columns",
        "qa_warning_columns",
    ):
        summary_df[column_name] = pd.to_numeric(summary_df[column_name], errors="coerce").fillna(0).astype(int)
    for column_name in ("qa_failed_observables", "qa_warning_reasons"):
        summary_df[column_name] = summary_df[column_name].fillna("")
    return summary_df


def apply_file_quality_status(
    file_df: pd.DataFrame,
    *,
    pass_column: str | None = None,
    timestamp_column: str = "qa_timestamp",
    in_scope_column: str = "qa_in_scope",
    epoch_column: str = "epoch_id",
) -> pd.DataFrame:
    """Populate file-level QA status columns from aggregated count columns."""
    out = file_df.copy()
    for column_name in (
        "qa_evaluated_columns",
        "qa_passed_columns",
        "qa_failed_columns",
        "qa_warning_columns",
    ):
        if column_name not in out.columns:
            out[column_name] = 0
        out[column_name] = pd.to_numeric(out[column_name], errors="coerce").fillna(0).astype(int)
    for column_name in ("qa_failed_observables", "qa_warning_reasons"):
        if column_name not in out.columns:
            out[column_name] = ""
        out[column_name] = out[column_name].fillna("")

    out["qa_pass_fraction"] = pd.Series(pd.NA, index=out.index, dtype="Float64")
    valid_mask = out["qa_evaluated_columns"] > 0
    out.loc[valid_mask, "qa_pass_fraction"] = (
        out.loc[valid_mask, "qa_passed_columns"] / out.loc[valid_mask, "qa_evaluated_columns"]
    ).astype(float)

    out["qa_status"] = "not_evaluated"
    qa_timestamp = pd.to_datetime(out[timestamp_column], errors="coerce") if timestamp_column in out.columns else pd.Series(pd.NaT, index=out.index)
    qa_in_scope = (
        out[in_scope_column].fillna(False).astype(bool)
        if in_scope_column in out.columns
        else pd.Series(False, index=out.index)
    )
    epoch_present = out[epoch_column].notna() if epoch_column in out.columns else pd.Series(False, index=out.index)

    invalid_mask = qa_timestamp.isna()
    out_of_scope_mask = (~invalid_mask) & (~qa_in_scope)
    no_epoch_mask = qa_in_scope & (~epoch_present)
    fail_mask = out["qa_failed_columns"] > 0
    warn_mask = (~fail_mask) & (out["qa_warning_columns"] > 0)
    pass_mask = (
        qa_in_scope
        & epoch_present
        & (out["qa_evaluated_columns"] > 0)
        & (out["qa_failed_columns"] == 0)
        & (out["qa_warning_columns"] == 0)
    )

    out.loc[invalid_mask, "qa_status"] = "invalid_timestamp"
    out.loc[out_of_scope_mask, "qa_status"] = "out_of_scope"
    out.loc[no_epoch_mask, "qa_status"] = "no_epoch_match"
    out.loc[warn_mask, "qa_status"] = "warn"
    out.loc[fail_mask, "qa_status"] = "fail"
    out.loc[pass_mask, "qa_status"] = "pass"

    if pass_column:
        out[pass_column] = out["qa_status"].eq("pass").astype(float)
    return out


def build_parameter_status_summary(
    df: pd.DataFrame,
    *,
    group_by: Sequence[str] | None = None,
    filename_column: str = "filename_base",
    parameter_column: str | None = None,
    evaluation_column: str = "evaluation_column",
    status_column: str = "status",
    reason_column: str = "reason",
    timestamp_column: str | None = None,
    example_limit: int = 12,
) -> pd.DataFrame:
    """Summarize how often each QA parameter is evaluated and fails."""
    if df.empty or status_column not in df.columns:
        return pd.DataFrame()

    resolved_parameter_column = parameter_column
    if resolved_parameter_column is None:
        resolved_parameter_column = "source_column" if "source_column" in df.columns else evaluation_column
    if resolved_parameter_column not in df.columns:
        return pd.DataFrame()

    group_columns = [str(column) for column in (group_by or [resolved_parameter_column]) if str(column) in df.columns]
    if resolved_parameter_column not in group_columns:
        group_columns.append(resolved_parameter_column)
    if not group_columns:
        return pd.DataFrame()

    use_columns = [*group_columns, status_column, resolved_parameter_column]
    if filename_column in df.columns:
        use_columns.append(filename_column)
    if evaluation_column in df.columns:
        use_columns.append(evaluation_column)
    if reason_column in df.columns:
        use_columns.append(reason_column)
    if timestamp_column and timestamp_column in df.columns:
        use_columns.append(timestamp_column)

    working = _with_status_flags(df[sorted(set(use_columns), key=use_columns.index)], status_column=status_column)
    if timestamp_column and timestamp_column in working.columns:
        working[timestamp_column] = pd.to_datetime(working[timestamp_column], errors="coerce")

    summary_df = (
        working.groupby(group_columns, dropna=False)
        .agg(
            observation_count=(status_column, "size"),
            evaluated_count=("_is_evaluated", "sum"),
            pass_count=("_is_pass", "sum"),
            fail_count=("_is_fail", "sum"),
            warning_count=("_is_warning", "sum"),
        )
        .reset_index()
    )

    if filename_column in working.columns:
        file_counts = (
            working.groupby(group_columns, dropna=False)[filename_column].nunique().rename("files_observed")
        )
        summary_df = summary_df.merge(file_counts.reset_index(), on=group_columns, how="left")

        file_status_df = (
            working.groupby(group_columns + [filename_column], dropna=False)
            .agg(
                file_has_fail=("_is_fail", "max"),
                file_has_warning=("_is_warning", "max"),
            )
            .reset_index()
        )
        failed_file_counts = (
            file_status_df.loc[file_status_df["file_has_fail"] > 0]
            .groupby(group_columns, dropna=False)[filename_column]
            .nunique()
            .rename("failed_file_count")
        )
        warning_file_counts = (
            file_status_df.loc[
                (file_status_df["file_has_fail"] == 0) & (file_status_df["file_has_warning"] > 0)
            ]
            .groupby(group_columns, dropna=False)[filename_column]
            .nunique()
            .rename("warning_file_count")
        )
        summary_df = summary_df.merge(failed_file_counts.reset_index(), on=group_columns, how="left")
        summary_df = summary_df.merge(warning_file_counts.reset_index(), on=group_columns, how="left")

    if evaluation_column in working.columns:
        scalar_component_counts = (
            working.groupby(group_columns, dropna=False)[evaluation_column]
            .nunique()
            .rename("scalar_component_count")
        )
        failing_scalar_counts = (
            working.loc[working["_is_fail"] == 1, group_columns + [evaluation_column]]
            .drop_duplicates()
            .groupby(group_columns, dropna=False)[evaluation_column]
            .nunique()
            .rename("failing_scalar_count")
        )
        evaluation_columns_text = (
            working.groupby(group_columns, dropna=False)[evaluation_column]
            .apply(lambda values: _join_unique(values, limit=example_limit))
            .rename("evaluation_columns")
        )
        failed_evaluation_columns = (
            working.loc[working["_is_fail"] == 1, group_columns + [evaluation_column]]
            .groupby(group_columns, dropna=False)[evaluation_column]
            .apply(lambda values: _join_unique(values, limit=example_limit))
            .rename("failed_evaluation_columns")
        )
        summary_df = summary_df.merge(scalar_component_counts.reset_index(), on=group_columns, how="left")
        summary_df = summary_df.merge(failing_scalar_counts.reset_index(), on=group_columns, how="left")
        summary_df = summary_df.merge(evaluation_columns_text.reset_index(), on=group_columns, how="left")
        summary_df = summary_df.merge(failed_evaluation_columns.reset_index(), on=group_columns, how="left")

    if reason_column in working.columns:
        non_pass_reasons = (
            working.loc[working[status_column].astype("string").fillna("").ne("pass"), group_columns + [reason_column]]
            .groupby(group_columns, dropna=False)[reason_column]
            .apply(_join_unique)
            .rename("non_pass_reasons")
        )
        summary_df = summary_df.merge(non_pass_reasons.reset_index(), on=group_columns, how="left")

    if timestamp_column and timestamp_column in working.columns:
        timestamp_summary = (
            working.groupby(group_columns, dropna=False)[timestamp_column]
            .agg(first_seen_timestamp="min", last_seen_timestamp="max")
            .reset_index()
        )
        fail_timestamps = (
            working.loc[working["_is_fail"] == 1, group_columns + [timestamp_column]]
            .groupby(group_columns, dropna=False)[timestamp_column]
            .agg(first_fail_timestamp="min", last_fail_timestamp="max")
            .reset_index()
        )
        summary_df = summary_df.merge(timestamp_summary, on=group_columns, how="left")
        summary_df = summary_df.merge(fail_timestamps, on=group_columns, how="left")

    for column_name in (
        "observation_count",
        "evaluated_count",
        "pass_count",
        "fail_count",
        "warning_count",
        "files_observed",
        "failed_file_count",
        "warning_file_count",
        "scalar_component_count",
        "failing_scalar_count",
    ):
        if column_name in summary_df.columns:
            summary_df[column_name] = pd.to_numeric(summary_df[column_name], errors="coerce").fillna(0).astype(int)
    if {"failed_file_count", "warning_file_count"} <= set(summary_df.columns):
        summary_df["non_pass_file_count"] = summary_df["failed_file_count"] + summary_df["warning_file_count"]

    summary_df["fail_fraction"] = pd.Series(pd.NA, index=summary_df.index, dtype="Float64")
    valid_mask = summary_df["evaluated_count"] > 0
    summary_df.loc[valid_mask, "fail_fraction"] = (
        summary_df.loc[valid_mask, "fail_count"] / summary_df.loc[valid_mask, "evaluated_count"]
    ).astype(float)

    for column_name in ("evaluation_columns", "failed_evaluation_columns", "non_pass_reasons"):
        if column_name in summary_df.columns:
            summary_df[column_name] = summary_df[column_name].fillna("")

    label_parts: list[str] = []
    if "step_display_name" in summary_df.columns:
        label_parts.append("step_display_name")
    elif "step_name" in summary_df.columns:
        label_parts.append("step_name")
    if "task_id" in summary_df.columns:
        label_parts.append("task_id")
    label_parts.append(resolved_parameter_column)

    def _parameter_label(row: pd.Series) -> str:
        tokens: list[str] = []
        for column_name in label_parts:
            value = row[column_name]
            if pd.isna(value):
                continue
            if column_name == "task_id":
                tokens.append(f"TASK_{int(value)}")
            else:
                text = str(value).strip()
                if text:
                    tokens.append(text)
        return " | ".join(tokens)

    summary_df["parameter_label"] = summary_df.apply(_parameter_label, axis=1)
    sort_columns = [
        column_name
        for column_name in ("failed_file_count", "fail_count", "warning_file_count", "warning_count", "parameter_label")
        if column_name in summary_df.columns
    ]
    ascending = [False, False, False, False, True][: len(sort_columns)]
    if sort_columns:
        summary_df = summary_df.sort_values(sort_columns, ascending=ascending, na_position="last")
    return summary_df.reset_index(drop=True)
