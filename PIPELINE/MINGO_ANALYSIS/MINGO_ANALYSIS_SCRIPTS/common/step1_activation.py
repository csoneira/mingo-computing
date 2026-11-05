from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd
from scipy.ndimage import gaussian_filter1d

ACTIVATION_METADATA_DECIMALS = 3


def _as_bool_matrix(arrays: Iterable[np.ndarray]) -> np.ndarray:
    matrix_parts = [np.asarray(arr, dtype=bool) for arr in arrays]
    if not matrix_parts:
        return np.empty((0, 0), dtype=bool)
    lengths = {part.shape[0] for part in matrix_parts}
    if len(lengths) != 1:
        raise ValueError("All boolean arrays must have the same length.")
    return np.column_stack(matrix_parts)


def _compute_conditional_matrix_from_bool_matrices(
    source_labels: list[str],
    source_matrix: np.ndarray,
    target_labels: list[str],
    target_matrix: np.ndarray,
) -> tuple[np.ndarray, dict[str, int]]:
    """Compute P(target | source) from pre-built boolean matrices."""
    if source_matrix.shape[0] != target_matrix.shape[0]:
        raise ValueError("Source and target boolean arrays must have the same number of events.")

    co_counts = source_matrix.T.astype(np.int64, copy=False) @ target_matrix.astype(
        np.int64,
        copy=False,
    )
    given_counts = source_matrix.sum(axis=0, dtype=np.int64).astype(int, copy=False)
    with np.errstate(divide="ignore", invalid="ignore"):
        cond = np.divide(
            co_counts.astype(float, copy=False),
            given_counts[:, None],
            out=np.full(co_counts.shape, np.nan, dtype=float),
            where=given_counts[:, None] > 0,
        )

    return cond, {
        label: int(given_counts[idx]) for idx, label in enumerate(source_labels)
    }


def compute_conditional_matrix_from_boolean_arrays(
    source_labels: list[str],
    source_arrays: list[np.ndarray],
    target_labels: list[str] | None = None,
    target_arrays: list[np.ndarray] | None = None,
) -> tuple[np.ndarray, dict[str, int]]:
    """Compute P(target | source) from boolean event-level arrays."""
    if target_labels is None:
        target_labels = source_labels
    if target_arrays is None:
        target_arrays = source_arrays

    if not source_labels or not source_arrays or not target_labels or not target_arrays:
        return np.empty((0, 0), dtype=float), {}

    source_matrix = _as_bool_matrix(source_arrays)
    target_matrix = _as_bool_matrix(target_arrays)
    return _compute_conditional_matrix_from_bool_matrices(
        source_labels,
        source_matrix,
        target_labels,
        target_matrix,
    )


def summarize_conditional_matrix(
    labels: list[str],
    matrix: np.ndarray,
    group_ids: list[int] | None = None,
) -> dict[str, float | str]:
    """Return compact scalar summaries for a square conditional matrix."""
    if (
        matrix.size == 0
        or matrix.ndim != 2
        or matrix.shape[0] != matrix.shape[1]
        or len(labels) != matrix.shape[0]
    ):
        return {
            "mean_off_diagonal": "",
            "max_off_diagonal": "",
            "mean_off_diagonal_cross_group": "",
        }

    n_items = matrix.shape[0]
    finite = np.isfinite(matrix)
    off_diag_mask = np.ones((n_items, n_items), dtype=bool)
    np.fill_diagonal(off_diag_mask, False)

    off_diag_values = matrix[finite & off_diag_mask]
    mean_off_diag = float(np.mean(off_diag_values)) if off_diag_values.size else ""
    max_off_diag = float(np.max(off_diag_values)) if off_diag_values.size else ""

    mean_cross_group: float | str = ""
    if group_ids is not None and len(group_ids) == n_items:
        group_arr = np.asarray(group_ids, dtype=int)
        cross_group_mask = off_diag_mask & (group_arr[:, None] != group_arr[None, :])
        cross_group_values = matrix[finite & cross_group_mask]
        if cross_group_values.size:
            mean_cross_group = float(np.mean(cross_group_values))

    return {
        "mean_off_diagonal": (
            round(mean_off_diag, ACTIVATION_METADATA_DECIMALS) if mean_off_diag != "" else ""
        ),
        "max_off_diagonal": (
            round(max_off_diag, ACTIVATION_METADATA_DECIMALS) if max_off_diag != "" else ""
        ),
        "mean_off_diagonal_cross_group": (
            round(mean_cross_group, ACTIVATION_METADATA_DECIMALS)
            if mean_cross_group != ""
            else ""
        ),
    }


def store_activation_matrix_metadata(
    metadata: dict[str, object],
    prefix: str,
    source_labels: list[str],
    matrix: np.ndarray,
    given_counts: dict[str, int],
    *,
    target_labels: list[str] | None = None,
    group_ids: list[int] | None = None,
) -> None:
    """Store matrix cells, source counts, and compact summaries under *prefix*."""
    if target_labels is None:
        target_labels = source_labels

    summary = summarize_conditional_matrix(
        source_labels if source_labels == target_labels else [],
        matrix,
        group_ids=group_ids if source_labels == target_labels else None,
    )
    metadata[f"{prefix}_mean_off_diagonal"] = summary["mean_off_diagonal"]
    metadata[f"{prefix}_max_off_diagonal"] = summary["max_off_diagonal"]
    metadata[f"{prefix}_mean_off_diagonal_cross_group"] = summary[
        "mean_off_diagonal_cross_group"
    ]

    for label in source_labels:
        metadata[f"{prefix}_given_count_{label}"] = int(given_counts.get(label, 0))

    if matrix.size == 0:
        return

    for i, src_label in enumerate(source_labels):
        for j, dst_label in enumerate(target_labels):
            value = matrix[i, j]
            metadata[f"{prefix}_{src_label}_to_{dst_label}"] = (
                round(float(value), ACTIVATION_METADATA_DECIMALS) if np.isfinite(value) else ""
            )


def compute_conditional_matrices_by_tt(
    tt_series: pd.Series,
    source_labels: list[str],
    source_arrays: list[np.ndarray],
    target_labels: list[str] | None = None,
    target_arrays: list[np.ndarray] | None = None,
    *,
    min_events: int = 30,
    max_tt_panels: int = 6,
) -> tuple[list[int], dict[int, np.ndarray], dict[int, dict[str, int]], dict[int, int]]:
    """Compute conditional matrices split by TT."""
    if target_labels is None:
        target_labels = source_labels
    if target_arrays is None:
        target_arrays = source_arrays

    if not source_labels or not source_arrays or not target_labels or not target_arrays:
        return [], {}, {}, {}

    tt_numeric = pd.to_numeric(tt_series, errors="coerce").fillna(0).astype(int)
    tt_counts = tt_numeric.value_counts()
    selected_tts = [
        int(tt)
        for tt, count in tt_counts.items()
        if int(tt) >= 10 and int(count) >= int(min_events)
    ][:max_tt_panels]
    if not selected_tts:
        return [], {}, {}, {}

    source_matrix = _as_bool_matrix(source_arrays)
    target_matrix = _as_bool_matrix(target_arrays)
    matrices: dict[int, np.ndarray] = {}
    given_counts_by_tt: dict[int, dict[str, int]] = {}
    event_counts_by_tt: dict[int, int] = {}

    for tt_value in selected_tts:
        mask_tt = (tt_numeric == int(tt_value)).to_numpy(dtype=bool)
        event_counts_by_tt[tt_value] = int(np.sum(mask_tt))
        cond, given_counts = _compute_conditional_matrix_from_bool_matrices(
            source_labels,
            source_matrix[mask_tt],
            target_labels,
            target_matrix[mask_tt],
        )
        matrices[tt_value] = cond
        given_counts_by_tt[tt_value] = given_counts

    return selected_tts, matrices, given_counts_by_tt, event_counts_by_tt


def store_activation_matrices_by_tt_metadata(
    metadata: dict[str, object],
    prefix: str,
    source_labels: list[str],
    target_labels: list[str],
    selected_tts: list[int],
    matrices: dict[int, np.ndarray],
    given_counts_by_tt: dict[int, dict[str, int]],
    event_counts_by_tt: dict[int, int],
) -> None:
    """Store TT-sliced activation matrices under *prefix*."""
    metadata[f"{prefix}_selected_tts"] = ",".join(str(tt) for tt in selected_tts)

    for tt_value in selected_tts:
        metadata[f"{prefix}_tt{tt_value}_event_count"] = int(event_counts_by_tt.get(tt_value, 0))
        given_counts = given_counts_by_tt.get(tt_value, {})
        for src_label in source_labels:
            metadata[f"{prefix}_tt{tt_value}_given_count_{src_label}"] = int(
                given_counts.get(src_label, 0)
            )

        matrix = matrices.get(tt_value)
        if matrix is None:
            continue
        for i, src_label in enumerate(source_labels):
            for j, dst_label in enumerate(target_labels):
                value = matrix[i, j]
                metadata[f"{prefix}_tt{tt_value}_{src_label}_to_{dst_label}"] = (
                    round(float(value), ACTIVATION_METADATA_DECIMALS)
                    if np.isfinite(value)
                    else ""
                )


def detect_streamer_threshold(
    df: pd.DataFrame,
    q_sum_cols: list[str],
    *,
    sigma: float = 3.0,
    n_bins: int = 300,
    search_start_quantile: float = 60.0,
) -> float | None:
    """Auto-detect the avalanche-streamer valley in pooled positive charge values."""
    values: list[np.ndarray] = []
    for column_name in q_sum_cols:
        if column_name not in df.columns:
            continue
        arr = pd.to_numeric(df[column_name], errors="coerce").to_numpy(dtype=float)
        arr = arr[np.isfinite(arr) & (arr > 0)]
        if arr.size:
            values.append(arr)

    if not values:
        return None

    pooled = np.concatenate(values)
    if pooled.size < 200:
        return None

    q_low = float(np.nanpercentile(pooled, 1.0))
    q_high = float(np.nanpercentile(pooled, 99.9))
    if q_high <= q_low:
        return None

    counts, edges = np.histogram(pooled, bins=n_bins, range=(q_low, q_high))
    centres = 0.5 * (edges[:-1] + edges[1:])
    smoothed = gaussian_filter1d(counts.astype(float), sigma=sigma)

    search_start = float(np.nanpercentile(pooled, search_start_quantile))
    start_idx = int(np.searchsorted(centres, search_start))
    start_idx = max(1, min(start_idx, len(smoothed) - 2))

    for idx in range(start_idx, len(smoothed) - 1):
        if smoothed[idx] < smoothed[idx - 1] and smoothed[idx] <= smoothed[idx + 1]:
            return float(centres[idx])

    return None
