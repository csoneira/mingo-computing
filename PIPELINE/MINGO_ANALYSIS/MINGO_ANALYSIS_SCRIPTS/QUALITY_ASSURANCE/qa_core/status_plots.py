"""Status plots for per-column and per-step QUALITY_ASSURANCE summaries."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

STATUS_COLORS = {
    "pass": "#2ca02c",
    "fail": "#d62728",
    "warn": "#f1c232",
    "no_epoch_match": "#7f7f7f",
    "out_of_scope": "#d9d9d9",
    "invalid_timestamp": "#111111",
    "not_evaluated": "#bdbdbd",
    "missing_reference": "#9e9e9e",
    "insufficient_reference": "#c7c7c7",
}


def _chunk_values(values: list[str], chunk_size: int) -> list[list[str]]:
    if chunk_size <= 0 or len(values) <= chunk_size:
        return [values]
    return [values[idx : idx + chunk_size] for idx in range(0, len(values), chunk_size)]


def _status_color(status: str) -> str:
    return STATUS_COLORS.get(str(status), "#7f7f7f")


def plot_column_status_grid(
    *,
    df: pd.DataFrame,
    x_column: str,
    y_column: str,
    status_column: str,
    out_path: Path,
    title: str,
    max_rows_per_plot: int = 120,
) -> list[Path]:
    """Plot red/green status dots over time for one row per QA column."""
    if df.empty or x_column not in df.columns or y_column not in df.columns or status_column not in df.columns:
        return []

    working = df[[x_column, y_column, status_column]].copy()
    working = working[working[x_column].notna() & working[y_column].notna()].copy()
    if working.empty:
        return []

    working = working.sort_values([x_column, y_column]).reset_index(drop=True)
    row_values = [str(value) for value in working[y_column].astype(str).unique().tolist()]
    created: list[Path] = []

    for chunk_index, row_chunk in enumerate(_chunk_values(row_values, max_rows_per_plot), start=1):
        y_lookup = {value: idx for idx, value in enumerate(row_chunk)}
        chunk_df = working[working[y_column].astype(str).isin(row_chunk)].copy()
        if chunk_df.empty:
            continue

        fig_height = min(22.0, max(4.0, 0.17 * len(row_chunk)))
        fig, ax = plt.subplots(figsize=(16.0, fig_height))
        y_positions = chunk_df[y_column].astype(str).map(y_lookup)
        colors = chunk_df[status_column].astype(str).map(_status_color)
        ax.scatter(
            chunk_df[x_column],
            y_positions,
            c=colors,
            s=18,
            marker="s",
            linewidths=0,
            alpha=0.9,
        )
        ax.set_yticks(list(range(len(row_chunk))))
        ax.set_yticklabels(row_chunk, fontsize=7)
        ax.grid(True, axis="x", alpha=0.25)
        ax.set_title(title if len(row_values) <= max_rows_per_plot else f"{title} ({chunk_index})")
        fig.autofmt_xdate(rotation=30)
        fig.tight_layout()

        out_file = out_path if len(row_values) <= max_rows_per_plot else out_path.with_name(f"{out_path.stem}_{chunk_index}{out_path.suffix}")
        out_file.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_file, dpi=160)
        plt.close(fig)
        created.append(out_file)

    return created


def plot_step_score_grid(
    *,
    df: pd.DataFrame,
    x_column: str,
    y_column: str,
    score_column: str,
    y_order: list[str],
    out_path: Path,
    title: str,
) -> Path | None:
    """Plot one row per step using a 0..1 success fraction color scale."""
    if df.empty or x_column not in df.columns or y_column not in df.columns or score_column not in df.columns:
        return None

    working = df[[x_column, y_column, score_column]].copy()
    working = working[working[x_column].notna() & working[y_column].notna()].copy()
    if working.empty:
        return None

    y_lookup = {value: idx for idx, value in enumerate(y_order)}
    working = working[working[y_column].isin(y_lookup)].copy()
    if working.empty:
        return None

    y_positions = working[y_column].map(y_lookup)
    fig_height = max(3.5, 0.75 * len(y_order))
    fig, ax = plt.subplots(figsize=(16.0, fig_height))

    finite_mask = pd.to_numeric(working[score_column], errors="coerce").notna()
    if finite_mask.any():
        scatter = ax.scatter(
            working.loc[finite_mask, x_column],
            y_positions.loc[finite_mask],
            c=pd.to_numeric(working.loc[finite_mask, score_column], errors="coerce"),
            cmap="RdYlGn",
            vmin=0.0,
            vmax=1.0,
            s=40,
            marker="s",
            linewidths=0,
        )
        fig.colorbar(scatter, ax=ax, label="Pass Fraction")
    if (~finite_mask).any():
        ax.scatter(
            working.loc[~finite_mask, x_column],
            y_positions.loc[~finite_mask],
            c="#bdbdbd",
            s=40,
            marker="s",
            linewidths=0,
        )

    ax.set_yticks(list(range(len(y_order))))
    ax.set_yticklabels(y_order)
    ax.grid(True, axis="x", alpha=0.25)
    ax.set_title(title)
    fig.autofmt_xdate(rotation=30)
    fig.tight_layout()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=160)
    plt.close(fig)
    return out_path


def plot_top_failing_parameters(
    *,
    df: pd.DataFrame,
    label_column: str,
    fail_count_column: str,
    warn_count_column: str,
    out_path: Path,
    title: str,
    top_n: int = 25,
) -> Path | None:
    """Plot the parameters with the highest number of failing/warning files."""
    required_columns = {label_column, fail_count_column, warn_count_column}
    if df.empty or not required_columns <= set(df.columns):
        return None

    working = df[[label_column, fail_count_column, warn_count_column]].copy()
    working[label_column] = working[label_column].astype("string").fillna("").str.strip()
    working[fail_count_column] = pd.to_numeric(working[fail_count_column], errors="coerce").fillna(0).astype(int)
    working[warn_count_column] = pd.to_numeric(working[warn_count_column], errors="coerce").fillna(0).astype(int)
    working = working[(working[label_column] != "") & ((working[fail_count_column] > 0) | (working[warn_count_column] > 0))]
    if working.empty:
        return None

    working = working.sort_values(
        [fail_count_column, warn_count_column, label_column],
        ascending=[False, False, True],
        na_position="last",
    ).head(max(1, top_n))
    working = working.iloc[::-1].reset_index(drop=True)

    fig_height = max(4.0, 0.38 * len(working))
    fig, ax = plt.subplots(figsize=(16.0, fig_height))
    y_positions = np.arange(len(working))
    fail_counts = working[fail_count_column].to_numpy(dtype=float)
    warn_counts = working[warn_count_column].to_numpy(dtype=float)

    ax.barh(y_positions, fail_counts, color=STATUS_COLORS["fail"], label="Failing files")
    ax.barh(y_positions, warn_counts, left=fail_counts, color=STATUS_COLORS["warn"], label="Warning files")

    totals = fail_counts + warn_counts
    for idx, total in enumerate(totals):
        if total <= 0:
            continue
        ax.text(total + 0.2, idx, f"{int(total)}", va="center", ha="left", fontsize=8)

    ax.set_yticks(y_positions)
    ax.set_yticklabels(working[label_column].tolist(), fontsize=8)
    ax.set_xlabel("Files with non-pass status")
    ax.set_title(title)
    ax.grid(True, axis="x", alpha=0.25)
    ax.legend(loc="best")
    fig.tight_layout()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=160)
    plt.close(fig)
    return out_path
