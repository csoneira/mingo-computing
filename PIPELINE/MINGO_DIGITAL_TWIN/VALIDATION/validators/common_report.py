#!/usr/bin/env python3

"""Reporting primitives for validation results and summaries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

RESULT_COLUMNS = [
    "run_timestamp",
    "validator",
    "test_id",
    "test_name",
    "step",
    "sim_run",
    "config_hash",
    "upstream_hash",
    "n_rows_in",
    "n_rows_out",
    "metric_name",
    "metric_value",
    "expected_value",
    "threshold_low",
    "threshold_high",
    "status",
    "notes",
]

SUMMARY_COLUMNS = [
    "run_timestamp",
    "validator",
    "step",
    "sim_run",
    "status",
    "n_pass",
    "n_warn",
    "n_fail",
    "n_skip",
    "n_error",
    "n_total",
]

VALID_STATUSES = {"PASS", "WARN", "FAIL", "SKIP", "ERROR"}


def sanitize_scalar(value: Any) -> Any:
    """Convert values to CSV-safe scalar forms."""
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        if isinstance(value, float) and (np.isnan(value) or np.isinf(value)):
            return None
        return value
    if isinstance(value, np.generic):
        out = value.item()
        if isinstance(out, float) and (np.isnan(out) or np.isinf(out)):
            return None
        return out
    if pd.isna(value):
        return None
    return str(value)


def normalize_tt_value(value: object) -> str:
    """Normalize truth-table-like values to a compact '1234' string."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    text = str(value).strip().replace(".0", "")
    if text in {"", "nan", "None", "<NA>"}:
        return ""
    return "".join(ch for ch in text if ch in "1234")


def normalize_tt_series(series: pd.Series) -> pd.Series:
    """Vectorized normalization for truth-table-like columns."""
    tt = series.astype("string").fillna("")
    tt = tt.str.strip().str.replace(".0", "", regex=False)
    tt = tt.replace({"nan": "", "None": "", "<NA>": ""})
    tt = tt.str.replace(r"[^1234]", "", regex=True)
    return tt


def overall_status_from_counts(counts: dict[str, int]) -> str:
    if counts.get("FAIL", 0) > 0:
        return "FAIL"
    if counts.get("ERROR", 0) > 0:
        return "ERROR"
    if counts.get("WARN", 0) > 0:
        return "WARN"
    if counts.get("PASS", 0) > 0:
        return "PASS"
    if counts.get("SKIP", 0) > 0:
        return "SKIP"
    return "ERROR"


@dataclass
class ResultBuilder:
    run_timestamp: str
    validator: str
    step: str
    sim_run: str | None
    config_hash: str | None
    upstream_hash: str | None
    n_rows_in: int | None
    n_rows_out: int | None

    def __post_init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def add(
        self,
        *,
        test_id: str,
        test_name: str,
        metric_name: str,
        metric_value: Any,
        status: str,
        expected_value: Any = None,
        threshold_low: Any = None,
        threshold_high: Any = None,
        notes: str = "",
        n_rows_in: int | None = None,
        n_rows_out: int | None = None,
    ) -> None:
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid status: {status}")
        row = {
            "run_timestamp": self.run_timestamp,
            "validator": self.validator,
            "test_id": test_id,
            "test_name": test_name,
            "step": self.step,
            "sim_run": self.sim_run,
            "config_hash": self.config_hash,
            "upstream_hash": self.upstream_hash,
            "n_rows_in": self.n_rows_in if n_rows_in is None else n_rows_in,
            "n_rows_out": self.n_rows_out if n_rows_out is None else n_rows_out,
            "metric_name": metric_name,
            "metric_value": sanitize_scalar(metric_value),
            "expected_value": sanitize_scalar(expected_value),
            "threshold_low": sanitize_scalar(threshold_low),
            "threshold_high": sanitize_scalar(threshold_high),
            "status": status,
            "notes": notes,
        }
        self.rows.append(row)

    def add_exception(self, *, test_id: str, test_name: str, exc: Exception) -> None:
        self.add(
            test_id=test_id,
            test_name=test_name,
            metric_name="exception",
            metric_value=type(exc).__name__,
            status="ERROR",
            notes=str(exc),
        )

    def to_frame(self) -> pd.DataFrame:
        if not self.rows:
            return pd.DataFrame(columns=RESULT_COLUMNS)
        df = pd.DataFrame(self.rows)
        return df.reindex(columns=RESULT_COLUMNS)


def summarize_results(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=SUMMARY_COLUMNS)

    records: list[dict[str, Any]] = []
    for (run_ts, validator), subdf in df.groupby(["run_timestamp", "validator"], dropna=False):
        counts = subdf["status"].value_counts().to_dict()
        counts = {k: int(v) for k, v in counts.items()}
        record = {
            "run_timestamp": run_ts,
            "validator": validator,
            "step": subdf["step"].iloc[0] if not subdf.empty else None,
            "sim_run": subdf["sim_run"].iloc[0] if not subdf.empty else None,
            "status": overall_status_from_counts(counts),
            "n_pass": counts.get("PASS", 0),
            "n_warn": counts.get("WARN", 0),
            "n_fail": counts.get("FAIL", 0),
            "n_skip": counts.get("SKIP", 0),
            "n_error": counts.get("ERROR", 0),
            "n_total": int(len(subdf)),
        }
        records.append(record)

    out = pd.DataFrame(records)
    return out.reindex(columns=SUMMARY_COLUMNS).sort_values(["validator"]).reset_index(drop=True)


def build_history_row(
    *,
    run_timestamp: str,
    run_name: str,
    summary_df: pd.DataFrame,
    sim_run_filter: str | None,
    selected_steps: str,
) -> dict[str, Any]:
    counts = {
        "PASS": int((summary_df["status"] == "PASS").sum()) if not summary_df.empty else 0,
        "WARN": int((summary_df["status"] == "WARN").sum()) if not summary_df.empty else 0,
        "FAIL": int((summary_df["status"] == "FAIL").sum()) if not summary_df.empty else 0,
        "SKIP": int((summary_df["status"] == "SKIP").sum()) if not summary_df.empty else 0,
        "ERROR": int((summary_df["status"] == "ERROR").sum()) if not summary_df.empty else 0,
    }
    overall = overall_status_from_counts(counts)
    return {
        "run_timestamp": run_timestamp,
        "run_name": run_name,
        "sim_run_filter": sim_run_filter,
        "selected_steps": selected_steps,
        "overall_status": overall,
        "validator_pass": counts["PASS"],
        "validator_warn": counts["WARN"],
        "validator_fail": counts["FAIL"],
        "validator_skip": counts["SKIP"],
        "validator_error": counts["ERROR"],
        "validator_total": int(len(summary_df)),
    }
