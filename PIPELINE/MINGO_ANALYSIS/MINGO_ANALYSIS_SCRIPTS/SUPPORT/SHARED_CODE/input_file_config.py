from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class InputFileConfigSelection:
    selected_conf: Optional[pd.Series]
    matching_confs: pd.DataFrame
    reason: str


def select_closest_valid_z_configuration(
    input_file: pd.DataFrame,
    *,
    reference_time: object,
) -> Optional[pd.Series]:
    """Return the nearest row with four finite, not-all-zero plane positions."""
    required = ["start", "P1", "P2", "P3", "P4"]
    if input_file.empty or any(column not in input_file.columns for column in required):
        return None

    work = input_file.copy()
    work["start_day"] = pd.to_datetime(
        work["start"], format="%Y-%m-%d", errors="coerce",
    ).dt.normalize()
    reference_day = pd.to_datetime(reference_time, errors="coerce")
    if pd.isna(reference_day):
        return None
    reference_day = reference_day.normalize()

    z_values = work[["P1", "P2", "P3", "P4"]].apply(
        pd.to_numeric, errors="coerce",
    )
    finite = np.isfinite(z_values.to_numpy(dtype=float)).all(axis=1)
    not_all_zero = z_values.ne(0).any(axis=1).to_numpy()
    valid = work.loc[work["start_day"].notna() & finite & not_all_zero].copy()
    if valid.empty:
        return None

    valid["delta"] = (valid["start_day"] - reference_day).abs()
    return valid.sort_values(
        by=["delta", "start_day"],
        ascending=[True, False],
        kind="mergesort",
    ).iloc[0].copy()


def select_input_file_configuration(
    input_file: pd.DataFrame,
    *,
    start_time: object,
    end_time: object,
) -> InputFileConfigSelection:
    """Select the effective run-dictionary configuration row.

    When boundary-day rows overlap, the configuration with the most recent
    start date wins so newer regimes supersede older ones deterministically.
    """
    if input_file.empty:
        return InputFileConfigSelection(
            selected_conf=None,
            matching_confs=input_file.iloc[0:0].copy(),
            reason="empty_input_file",
        )

    work = input_file.copy()
    work["start"] = pd.to_datetime(work["start"], format="%Y-%m-%d", errors="coerce")
    work["end"] = pd.to_datetime(work["end"], format="%Y-%m-%d", errors="coerce")
    work["end"] = work["end"].fillna(pd.Timestamp.now())
    work["start_day"] = work["start"].dt.normalize()
    work["end_day"] = work["end"].dt.normalize()

    start_day = pd.to_datetime(start_time, errors="coerce").normalize()
    end_day = pd.to_datetime(end_time, errors="coerce").normalize()

    matching_confs = work[(work["start_day"] <= start_day) & (work["end_day"] >= end_day)].copy()
    if not matching_confs.empty:
        selected_conf = matching_confs.sort_values(
            by=["start_day", "end_day"],
            ascending=[False, False],
            kind="mergesort",
        ).iloc[0].copy()
        reason = "exact_overlap_latest_start" if len(matching_confs) > 1 else "exact"
        return InputFileConfigSelection(
            selected_conf=selected_conf,
            matching_confs=matching_confs,
            reason=reason,
        )

    before = work[work["start_day"] <= end_day].sort_values(
        by=["start_day", "end_day"],
        ascending=[False, False],
        kind="mergesort",
    )
    if not before.empty:
        return InputFileConfigSelection(
            selected_conf=before.iloc[0].copy(),
            matching_confs=matching_confs,
            reason="closest_before",
        )

    earliest = work.sort_values(
        by=["start", "end"],
        ascending=[True, True],
        kind="mergesort",
    )
    if earliest.empty:
        return InputFileConfigSelection(
            selected_conf=None,
            matching_confs=matching_confs,
            reason="no_valid_rows",
        )
    return InputFileConfigSelection(
        selected_conf=earliest.iloc[0].copy(),
        matching_confs=matching_confs,
        reason="earliest_available",
    )
