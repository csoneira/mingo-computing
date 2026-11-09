#!/usr/bin/env python3
"""Apply the initial, deliberately small calibration chain to self-trigger data.

The script consumes ``selftrigger_cleaned_*.parquet`` from self-trigger Task 1,
applies configured broad channel-value filters and four supplied offset
matrices, then writes ``selftrigger_calibrated_*.parquet``. It does not fit or
derive any calibration constants.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime
import json
import random
from pathlib import Path
import re
import shutil
import sys
import time

import numpy as np
import pandas as pd
import yaml
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

CURRENT_PATH = Path(__file__).resolve()
SCRIPTS_ROOT = next(parent for parent in CURRENT_PATH.parents if parent.name == "MINGO_ANALYSIS_SCRIPTS")
REPO_ROOT = next(
    parent
    for parent in SCRIPTS_ROOT.parents
    if (parent / "CONTEXTUAL/CONFIG/CONTENTS/environment/dataflow.sh").is_file()
)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.debug_plots import plot_debug_histograms
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.file_selection import select_latest_candidate
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.path_config import get_repo_root
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.plot_utils import runtime_plot_directory_name
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.step1_shared import (
    add_normalized_count_metadata,
    apply_step1_master_overrides,
    build_events_per_second_metadata,
    canonicalize_step1_columns,
    prune_redundant_count_metadata,
    save_metadata,
)
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.status_csv import initialize_status_row, update_status_progress


TASK_NAME = "TASK_2_SELFTRIGGER"
INPUT_PREFIX = "selftrigger_cleaned_"
OUTPUT_PREFIX = "selftrigger_calibrated_"
CHANNEL_COLUMN = re.compile(r"p[1-4]_s[1-4]_e[fb]_[qt]$", re.IGNORECASE)
PLOT_ALIASES = (
    "raw_channel_spectra",
    "tdif_spectra",
    "tsum_spectra",
    "charge_spectra",
    "cross_plane_delta_tsum",
    "charge_spectra_selftrigger_one_plane_topologies",
)


def _load_yaml(path: Path) -> dict:
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(value, dict):
        raise ValueError(f"Expected a YAML mapping in {path}")
    return value


def _directories(station: int, repo_root: Path) -> dict[str, Path]:
    step_root = (
        repo_root / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS" / f"MINGO{station:02d}"
        / "STAGE_1" / "EVENT_DATA" / "STEP_1"
    )
    task_root = step_root / TASK_NAME
    input_root = task_root / "INPUT_FILES"
    return {
        "task_root": task_root,
        "task1_output": step_root / "TASK_1_SELFTRIGGER" / "OUTPUT_FILES",
        "task1_metadata": step_root / "TASK_1_SELFTRIGGER" / "METADATA" / "task_1_metadata_execution.csv",
        "unprocessed": input_root / "UNPROCESSED_DIRECTORY",
        "processing": input_root / "PROCESSING_DIRECTORY",
        "completed": input_root / "COMPLETED_DIRECTORY",
        "error": input_root / "ERROR_DIRECTORY",
        "output": task_root / "OUTPUT_FILES",
        "metadata": task_root / "METADATA",
        "plots": task_root / "PLOTS" / "DEBUG_PLOTS",
    }


def _raw_strip_activity_and_qsum(
    frame: pd.DataFrame,
) -> tuple[dict[int, np.ndarray], dict[int, np.ndarray]]:
    """Snapshot strip activity and raw Q_sum before safety filtering."""
    activity: dict[int, np.ndarray] = {}
    qsum: dict[int, np.ndarray] = {}
    for plane in range(1, 5):
        plane_activity = []
        plane_qsum = []
        for strip in range(1, 5):
            qf = pd.to_numeric(
                frame[f"p{plane}_s{strip}_ef_q"], errors="coerce"
            ).to_numpy(dtype=float)
            qb = pd.to_numeric(
                frame[f"p{plane}_s{strip}_eb_q"], errors="coerce"
            ).to_numpy(dtype=float)
            active = (
                (np.isfinite(qf) & (qf != 0))
                | (np.isfinite(qb) & (qb != 0))
            )
            plane_activity.append(active)
            plane_qsum.append((qf + qb) / 2.0)
        activity[plane] = np.column_stack(plane_activity)
        qsum[plane] = np.column_stack(plane_qsum)
    return activity, qsum


def _plot_selftrigger_tt_charge_comparison(
    frame: pd.DataFrame,
    tt_codes: np.ndarray,
    active_by_plane: dict[int, np.ndarray],
    raw_qsum_by_plane: dict[int, np.ndarray],
    *,
    station: int,
    basename: str,
    out_dir: Path,
    fig_index: int,
) -> Path:
    """Plot charge spectra for strict one-plane self-trigger topology classes."""
    edges = np.linspace(80.0, 120.0, 161)
    single_plane_populations = (
        ("single_strip", "One strip", "tab:purple"),
        ("three_strips", "Three strips", "tab:pink"),
        ("four_strips", "Four strips", "tab:cyan"),
        ("three_strip_min", "Three strips · minimum only", "tab:olive"),
        ("four_strip_min", "Four strips · minimum only", "tab:gray"),
    )
    fig, axes = plt.subplots(4, 8, figsize=(28, 16), sharex=True, sharey=True, squeeze=False)
    legend_handles = [Line2D([], [], color=color, label=label)
                      for _, label, color in single_plane_populations]
    for plane in range(1, 5):
        plane_active = active_by_plane[plane]
        plane_qsum = raw_qsum_by_plane[plane]
        finite_active = plane_active & np.isfinite(plane_qsum)
        finite_active_count = np.count_nonzero(finite_active, axis=1)
        minimum = np.min(
            np.where(finite_active, plane_qsum, np.inf), axis=1
        )
        plane_tt = tt_codes == plane
        active_count = np.count_nonzero(plane_active, axis=1)
        single_plane_masks = {
            "single_strip": (
                plane_tt & (active_count == 1)
            )[:, np.newaxis] & plane_active,
            "three_strips": (
                plane_tt & (active_count == 3)
            )[:, np.newaxis] & plane_active,
            "four_strips": (
                plane_tt & (active_count == 4)
            )[:, np.newaxis] & plane_active,
            "three_strip_min": (
                plane_tt & (active_count == 3) & (finite_active_count == 3)
            )[:, np.newaxis]
            & finite_active
            & (plane_qsum == minimum[:, np.newaxis]),
            "four_strip_min": (
                plane_tt & (active_count == 4) & (finite_active_count == 4)
            )[:, np.newaxis]
            & finite_active
            & (plane_qsum == minimum[:, np.newaxis]),
        }
        for strip in range(1, 5):
            for side_index, (side, suffix) in enumerate((("F", "ef_q"), ("B", "eb_q"))):
                column_index = (strip - 1) * 2 + side_index
                ax = axes[plane - 1, column_index]
                ax.set_title(f"{side} · S{strip}", fontsize=8)
                # A strict TTn event has activity in plane n and none in the
                # other planes. Only plot it in that plane's row.
                channel = f"p{plane}_s{strip}_{suffix}"
                one_plane_histograms = {}
                one_plane_counts = {}
                if channel in frame.columns:
                    for key, _label, _color in single_plane_populations:
                        values = pd.to_numeric(
                            frame.loc[single_plane_masks[key][:, strip - 1], channel],
                            errors="coerce",
                        ).to_numpy(dtype=float)
                        values = values[np.isfinite(values) & (values != 0)]
                        counts, _ = np.histogram(values, bins=edges)
                        count = int(counts.sum())
                        normalized_counts = (
                            counts / counts.max()
                            if counts.size and counts.max()
                            else np.zeros_like(counts, dtype=float)
                        )
                        one_plane_histograms[key] = normalized_counts
                        one_plane_counts[key] = count
                for key, label, color in single_plane_populations:
                    normalized_counts = one_plane_histograms.get(key)
                    if normalized_counts is not None and one_plane_counts.get(key, 0):
                        ax.stairs(
                            normalized_counts,
                            edges,
                            color=color,
                            linewidth=1.2,
                        )
                if column_index == 0:
                    ax.set_ylabel(f"P{plane}\nCounts / max", fontsize=8)
                if plane == 4:
                    ax.set_xlabel("Raw charge (ADC)")
                ax.set_xlim(float(edges[0]), float(edges[-1]))
                ax.grid(True, alpha=0.2)
                count_lines = [
                    f"{label}: N={one_plane_counts.get(key, 0)}"
                    for key, label, _color in single_plane_populations
                ]
                ax.text(
                    0.98, 0.96,
                    "\n".join(count_lines),
                    ha="right", va="top", transform=ax.transAxes, fontsize=5,
                )

    fig.legend(
        handles=legend_handles,
        loc="upper center",
        ncol=4,
        frameon=False,
        bbox_to_anchor=(0.5, 0.965),
        fontsize=8,
    )
    fig.suptitle(
        f"One-plane self-trigger charge spectra by strip topology · MINGO{station:02d}\n"
        "Each channel is normalized to its own maximum count over 80–120 ADC; three/four-strip minimum curves retain only the "
        "minimum-charge strip. Every row uses only strict TT1, TT2, TT3 or TT4 events for that plane.",
        fontsize=12,
        y=0.995,
    )
    fig.tight_layout(rect=[0.02, 0.02, 0.99, 0.91])
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / (
        f"{fig_index:02d}_debug_TASK_2_SELFTRIGGER_"
        f"charge_spectra_selftrigger_one_plane_topologies_{basename}.png"
    )
    fig.savefig(output_path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return output_path


def _move(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite staged file: {destination}")
    shutil.move(str(source), str(destination))


def _confirmed_task1_outputs(metadata_path: Path) -> set[str]:
    if not metadata_path.is_file():
        return set()
    confirmed: set[str] = set()
    with metadata_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            output_path = str(row.get("output_path", "") or "").strip()
            if output_path:
                confirmed.add(Path(output_path).name)
    return confirmed


def _stage_inputs(
    directories: dict[str, Path],
    explicit_input: str | None,
    *,
    complete_reanalysis: bool,
    selection_mode: str,
    station: int,
) -> str | None:
    for name in ("unprocessed", "processing", "completed", "error", "output", "metadata", "plots"):
        directories[name].mkdir(parents=True, exist_ok=True)

    if explicit_input:
        source = Path(explicit_input).expanduser().resolve()
        if not source.is_file() or not source.name.startswith(INPUT_PREFIX) or source.suffix.lower() != ".parquet":
            raise ValueError(f"Input must be an existing {INPUT_PREFIX}*.parquet: {source}")
        task1_root = directories["task1_output"].resolve()
        unprocessed_root = directories["unprocessed"].resolve()
        if task1_root in source.parents:
            target = directories["unprocessed"] / source.name
            if not target.exists():
                shutil.copy2(source, target)
        elif unprocessed_root not in source.parents:
            raise ValueError(f"Input must come from self-trigger Task 1 OUTPUT_FILES or this task's UNPROCESSED_DIRECTORY: {source}")
        return source.name

    known_names = {
        path.name
        for folder in (directories["unprocessed"], directories["processing"], directories["completed"])
        for path in folder.glob(f"{INPUT_PREFIX}*.parquet")
    }
    completed_outputs = {
        path.name for path in directories["completed"].glob(f"{INPUT_PREFIX}*.parquet")
    }
    produced_names = _confirmed_task1_outputs(directories["task1_metadata"])
    for source in directories["task1_output"].glob(f"{INPUT_PREFIX}*.parquet"):
        if source.name not in produced_names or source.name in known_names:
            continue
        output_name = OUTPUT_PREFIX + source.name[len(INPUT_PREFIX):]
        output_exists = (directories["output"] / output_name).exists()
        if complete_reanalysis or not output_exists:
            shutil.copy2(source, directories["unprocessed"] / source.name)

    unprocessed = list(directories["unprocessed"].glob(f"{INPUT_PREFIX}*.parquet"))
    processing = list(directories["processing"].glob(f"{INPUT_PREFIX}*.parquet"))
    if not unprocessed and not processing and complete_reanalysis and completed_outputs:
        selected = (
            random.choice(list(completed_outputs))
            if selection_mode == "random"
            else select_latest_candidate(sorted(completed_outputs), station) or sorted(completed_outputs)[-1]
        )
        source = directories["completed"] / selected
        _move(source, directories["unprocessed"] / source.name)
    return None


def _load_plot_aliases(path: Path) -> set[str]:
    config = _load_yaml(path)
    enabled, disabled = config.get("plots"), config.get("non_plots")
    if not isinstance(enabled, list) or not isinstance(disabled, list):
        raise ValueError(f"{path} must define 'plots' and 'non_plots' lists")
    enabled, disabled = [str(value) for value in enabled], [str(value) for value in disabled]
    if len(enabled) != len(set(enabled)) or len(disabled) != len(set(disabled)):
        raise ValueError(f"Duplicate plot alias in {path}")
    if set(enabled) & set(disabled) or set(enabled) | set(disabled) != set(PLOT_ALIASES):
        raise ValueError(f"Plot lists must partition {PLOT_ALIASES}; enabled={enabled}, disabled={disabled}")
    return set(enabled)


def _load_filter_config(path: Path) -> dict:
    config = _load_yaml(path).get("filtering", {})
    if not isinstance(config, dict):
        raise ValueError(f"{path}: filtering must be a mapping")
    action = str(config.get("action", "zero_out_of_range")).strip().lower()
    if action != "zero_out_of_range":
        raise ValueError(f"{path}: unsupported filtering.action {action!r}")
    ranges = {}
    for key in ("charge", "time"):
        pair = config.get(key)
        if not isinstance(pair, list) or len(pair) != 2:
            raise ValueError(f"{path}: filtering.{key} must be [lower, upper]")
        low, high = map(float, pair)
        if not np.isfinite(low) or not np.isfinite(high) or low >= high:
            raise ValueError(f"{path}: filtering.{key} must contain finite increasing limits")
        ranges[key] = (low, high)
    return {**config, "action": action, "charge": ranges["charge"], "time": ranges["time"]}


def _load_calibration_matrices(path: Path) -> dict[str, np.ndarray]:
    raw = _load_yaml(path).get("matrices", {})
    expected = ("tdif", "tsum", "qf", "qb")
    if not isinstance(raw, dict) or set(raw) != set(expected):
        raise ValueError(f"{path}: matrices must define exactly {expected}")
    matrices: dict[str, np.ndarray] = {}
    for key in expected:
        values = np.asarray(raw[key], dtype=float)
        if values.shape != (4, 4) or not np.isfinite(values).all():
            raise ValueError(f"{path}: matrices.{key} must be a finite 4x4 matrix")
        matrices[key] = values
    return matrices


def _apply_safety_filter(frame: pd.DataFrame, config: dict) -> dict[str, int]:
    counts = {"charge_values_zeroed": 0, "time_values_zeroed": 0}
    if not bool(config.get("enabled", True)):
        return counts
    for column in frame.columns:
        match = CHANNEL_COLUMN.fullmatch(str(column))
        if match is None:
            continue
        quantity = "charge" if str(column).lower().endswith("_q") else "time"
        low, high = config[quantity]
        values = pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype=float)
        outside = np.isfinite(values) & ((values < low) | (values > high))
        counts[f"{quantity}_values_zeroed"] += int(outside.sum())
        if outside.any():
            filtered = values.copy()
            filtered[outside] = 0.0
            frame.loc[:, column] = filtered
    return counts


def _require_input_channels(frame: pd.DataFrame, source: Path) -> None:
    required = [
        f"p{plane}_s{strip}_e{end}_{quantity}"
        for plane in range(1, 5)
        for strip in range(1, 5)
        for end in ("f", "b")
        for quantity in ("q", "t")
    ]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"Self-trigger Task 2 input {source.name} is missing channel columns: {', '.join(missing)}")


def _build_and_calibrate_components(frame: pd.DataFrame, matrices: dict[str, np.ndarray]) -> None:
    for plane in range(1, 5):
        for strip in range(1, 5):
            qf = pd.to_numeric(frame[f"p{plane}_s{strip}_ef_q"], errors="coerce").to_numpy(dtype=float)
            qb = pd.to_numeric(frame[f"p{plane}_s{strip}_eb_q"], errors="coerce").to_numpy(dtype=float)
            tf = pd.to_numeric(frame[f"p{plane}_s{strip}_ef_t"], errors="coerce").to_numpy(dtype=float)
            tb = pd.to_numeric(frame[f"p{plane}_s{strip}_eb_t"], errors="coerce").to_numpy(dtype=float)

            # Zero is the inactive-channel sentinel throughout STEP_1. Apply
            # offsets only to nonzero end values so absent channels stay zero.
            qf_cal = np.where(
                qf == 0.0, 0.0, qf - matrices["qf"][plane - 1, strip - 1]
            )
            qb_cal = np.where(
                qb == 0.0, 0.0, qb - matrices["qb"][plane - 1, strip - 1]
            )
            tsum = (tf + tb) / 2.0
            tdif = (tb - tf) / 2.0
            qsum = (qf + qb) / 2.0
            qdif = (qf - qb) / 2.0

            frame.loc[:, f"p{plane}_s{strip}_qf"] = qf
            frame.loc[:, f"p{plane}_s{strip}_qb"] = qb
            frame.loc[:, f"p{plane}_s{strip}_qsum"] = qsum
            frame.loc[:, f"p{plane}_s{strip}_qdif"] = qdif
            frame.loc[:, f"p{plane}_s{strip}_qf_cal"] = qf_cal
            frame.loc[:, f"p{plane}_s{strip}_qb_cal"] = qb_cal
            frame.loc[:, f"p{plane}_s{strip}_qsum_cal"] = (qf_cal + qb_cal) / 2.0
            frame.loc[:, f"p{plane}_s{strip}_qdif_cal"] = (qf_cal - qb_cal) / 2.0
            frame.loc[:, f"p{plane}_s{strip}_tsum"] = tsum
            frame.loc[:, f"p{plane}_s{strip}_tdif"] = tdif
            time_active = (tf != 0.0) | (tb != 0.0)
            frame.loc[:, f"p{plane}_s{strip}_tsum_cal"] = np.where(
                time_active,
                tsum + matrices["tsum"][plane - 1, strip - 1],
                0.0,
            )
            frame.loc[:, f"p{plane}_s{strip}_tdif_cal"] = np.where(
                time_active,
                tdif - matrices["tdif"][plane - 1, strip - 1],
                0.0,
            )


def _add_cross_plane_delta_tsum(frame: pd.DataFrame) -> list[str]:
    plane_time_columns: dict[int, np.ndarray] = {}
    for plane in range(1, 5):
        times = np.column_stack([
            pd.to_numeric(frame[f"p{plane}_s{strip}_tsum_cal"], errors="coerce").to_numpy(dtype=float)
            for strip in range(1, 5)
        ])
        front = np.column_stack([
            pd.to_numeric(frame[f"p{plane}_s{strip}_qf_cal"], errors="coerce").to_numpy(dtype=float)
            for strip in range(1, 5)
        ])
        back = np.column_stack([
            pd.to_numeric(frame[f"p{plane}_s{strip}_qb_cal"], errors="coerce").to_numpy(dtype=float)
            for strip in range(1, 5)
        ])
        active = np.isfinite(times) & np.isfinite(front) & np.isfinite(back) & ((front != 0) | (back != 0)) & (times != 0)
        counts = active.sum(axis=1)
        plane_times = np.divide(
            np.where(active, times, 0.0).sum(axis=1),
            counts,
            out=np.full(len(frame), np.nan, dtype=float),
            where=counts > 0,
        )
        plane_time_columns[plane] = plane_times

    columns: list[str] = []
    for first_plane in range(1, 5):
        for second_plane in range(first_plane + 1, 5):
            name = f"delta_tsum_p{first_plane}_p{second_plane}"
            frame.loc[:, name] = plane_time_columns[second_plane] - plane_time_columns[first_plane]
            columns.append(name)
    return columns


def _data_time_metadata(frame: pd.DataFrame) -> dict[str, object]:
    if "datetime" not in frame.columns:
        return {"data_first_datetime": "", "data_last_datetime": "", "data_duration_seconds": 0}
    values = pd.to_datetime(frame["datetime"], errors="coerce").dropna()
    if values.empty:
        return {"data_first_datetime": "", "data_last_datetime": "", "data_duration_seconds": 0}
    first, last = values.min(), values.max()
    return {
        "data_first_datetime": first.isoformat(),
        "data_last_datetime": last.isoformat(),
        "data_duration_seconds": max(0, int((last - first).total_seconds())),
    }


def _selftrigger_tt_codes(frame: pd.DataFrame) -> np.ndarray:
    """Encode active planes from the filtered front/back charge channels."""
    plane_hits = []
    for plane in range(1, 5):
        columns = [
            f"p{plane}_s{strip}_{side}"
            for strip in range(1, 5)
            for side in ("qf", "qb")
        ]
        missing = [column for column in columns if column not in frame.columns]
        if missing:
            raise ValueError(f"Cannot calculate self-trigger TT rates; missing charge columns: {missing}")
        values = frame[columns].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
        plane_hits.append((np.isfinite(values) & (values != 0)).any(axis=1))

    hit_matrix = np.column_stack(plane_hits)
    return np.asarray([
        int("".join(str(plane + 1) for plane, active in enumerate(row) if active) or "0")
        for row in hit_matrix
    ], dtype=int)


def _raw_channel_tt_codes(frame: pd.DataFrame) -> np.ndarray:
    """Classify event TT from the unfiltered Task-1 channel charges."""
    if "tt_task0_raw" in frame.columns:
        saved_tt = pd.to_numeric(frame["tt_task0_raw"], errors="coerce").to_numpy(dtype=float)
        if np.isfinite(saved_tt).all():
            return np.rint(saved_tt).astype(int)
    plane_hits = []
    for plane in range(1, 5):
        columns = [
            f"p{plane}_s{strip}_e{side}_q"
            for strip in range(1, 5)
            for side in ("f", "b")
        ]
        values = frame[columns].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
        plane_hits.append((np.isfinite(values) & (values != 0)).any(axis=1))
    hit_matrix = np.column_stack(plane_hits)
    return np.asarray([
        int("".join(str(plane + 1) for plane, active in enumerate(row) if active) or "0")
        for row in hit_matrix
    ], dtype=int)


def _trigger_metadata(frame: pd.DataFrame, basename: str, execution_id: str) -> dict[str, object]:
    result: dict[str, object] = {"filename_base": basename, "execution_timestamp": execution_id}
    for column in ("tt_task0_acq", "tt_task0_raw"):
        if column not in frame.columns:
            continue
        counts = pd.to_numeric(frame[column], errors="coerce").dropna().round().astype(int).value_counts().sort_index()
        for trigger, count in counts.items():
            result[f"{column}_{trigger}_count"] = int(count)

    timestamps = pd.to_datetime(frame["datetime"], errors="coerce") if "datetime" in frame.columns else pd.Series(pd.NaT, index=frame.index)
    valid_time = timestamps.notna().to_numpy()
    active_seconds = int(timestamps.loc[valid_time].dt.floor("s").nunique())
    tt_codes = _selftrigger_tt_codes(frame)
    result["tt_task2_selftrigger_active_seconds"] = active_seconds
    result["count_rate_denominator_seconds"] = active_seconds
    result["tt_task2_selftrigger_rate_denominator_basis"] = "distinct_valid_event_seconds"
    for trigger in (0, 1, 2, 3, 4, 12, 13, 14, 23, 24, 34, 123, 124, 134, 234, 1234):
        count = int(((tt_codes == trigger) & valid_time).sum())
        result[f"tt_task2_selftrigger_{trigger}_count"] = count
        result[f"tt_task2_selftrigger_{trigger}_rate_hz"] = (
            round(count / active_seconds, 6) if active_seconds > 0 else 0.0
        )
    return result


def process_one(station: int, explicit_input: str | None = None, *, verbose: bool = False) -> int:
    repo_root = get_repo_root()
    config_root = SCRIPTS_ROOT / "SUPPORT/CONFIG_FILES/STAGE_1/EVENT_DATA/STEP_1/TASK_2_SELFTRIGGER"
    config = apply_step1_master_overrides(_load_yaml(config_root / "config_task_2_selftrigger.yaml"))
    if station not in {int(value) for value in config.get("selection", {}).get("stations", range(5))}:
        print(f"Station {station} is disabled by config_task_2_selftrigger.yaml")
        return 0
    aliases = _load_plot_aliases(config_root / "config_plots_task_2_selftrigger.yaml")
    filter_file = config_root / str(config.get("filtering_config_yaml", "config_filtering_task_2_selftrigger.yaml"))
    calibration_file = config_root / str(config.get("calibration_config_yaml", "config_calibration_task_2_selftrigger.yaml"))
    filter_config = _load_filter_config(filter_file)
    matrices = _load_calibration_matrices(calibration_file)

    selection_mode = str(config.get("file_selection_mode", "new")).strip().lower()
    if selection_mode not in {"qa", "new", "random"}:
        raise ValueError(f"Self-trigger Task 2 file_selection_mode must be qa, new, or random, got {selection_mode!r}")
    complete_reanalysis = bool(config.get("complete_reanalysis", False))
    force_replacement = bool(config.get("force_replacement", False))
    print(
        "Self-trigger Task 2 effective settings: "
        f"complete_reanalysis={complete_reanalysis}, file_selection_mode={selection_mode}, "
        f"create_plots={bool(config.get('create_plots', True))}"
    )
    directories = _directories(station, repo_root)
    explicit_name = _stage_inputs(
        directories,
        explicit_input,
        complete_reanalysis=complete_reanalysis,
        selection_mode=selection_mode,
        station=station,
    )
    candidates = list(directories["unprocessed"].glob(f"{INPUT_PREFIX}*.parquet"))
    if not candidates:
        print(f"No {INPUT_PREFIX}*.parquet inputs are ready for MINGO{station:02d}.")
        return 0
    if explicit_name is not None:
        input_path = directories["unprocessed"] / explicit_name
        if not input_path.is_file():
            raise FileNotFoundError(f"Explicit self-trigger Task 2 input was not staged: {input_path}")
    else:
        input_path = (
            random.choice(candidates)
            if selection_mode == "random"
            else Path(select_latest_candidate([path.name for path in candidates], station) or candidates[-1].name)
        )
    if not input_path.is_absolute():
        input_path = directories["unprocessed"] / input_path
    processing_path = directories["processing"] / input_path.name
    _move(input_path, processing_path)
    basename = processing_path.name[len(INPUT_PREFIX):-len(processing_path.suffix)]
    output_path = directories["output"] / f"{OUTPUT_PREFIX}{basename}.parquet"
    if output_path.exists() and not force_replacement and not complete_reanalysis:
        _move(processing_path, directories["completed"] / processing_path.name)
        print(f"Output already exists; archived duplicate input without replacement: {output_path}")
        return 0

    execution_time = datetime.now()
    execution_id = execution_time.strftime("%Y-%m-%d_%H.%M.%S")
    status_path = directories["metadata"] / "task_2_metadata_status.csv"
    initialize_status_row(status_path, basename, execution_id, completion_fraction=0.05)
    start = time.perf_counter()
    read_seconds = plot_seconds = write_seconds = 0.0
    saved_plots: list[Path] = []
    try:
        read_start = time.perf_counter()
        working_df = canonicalize_step1_columns(pd.read_parquet(processing_path, engine="pyarrow"))
        read_seconds = time.perf_counter() - read_start
        if working_df.empty:
            raise ValueError("Task 1 self-trigger input parquet contains no rows")
        _require_input_channels(working_df, processing_path)
        raw_tt_codes = _raw_channel_tt_codes(working_df)
        raw_active_by_plane, raw_qsum_by_plane = _raw_strip_activity_and_qsum(
            working_df
        )
        update_status_progress(status_path, basename, execution_id, 0.20)

        filter_metrics = _apply_safety_filter(working_df, filter_config)
        _build_and_calibrate_components(working_df, matrices)
        delta_columns = _add_cross_plane_delta_tsum(working_df)
        update_status_progress(status_path, basename, execution_id, 0.45)

        if verbose:
            print(
                f"Self-trigger Task 2 station={station} rows={len(working_df)} "
                f"filter_enabled={bool(filter_config.get('enabled', True))} "
                f"zeroed_Q={filter_metrics['charge_values_zeroed']} "
                f"zeroed_T={filter_metrics['time_values_zeroed']}"
            )

        plot_dir = directories["plots"] / runtime_plot_directory_name(basename, execution_id)
        plot_start = time.perf_counter()
        plot_groups = {
            "raw_channel_spectra": [str(column) for column in working_df.columns if CHANNEL_COLUMN.fullmatch(str(column))],
            "tdif_spectra": [
                f"p{plane}_s{strip}_tdif{suffix}"
                for plane in range(1, 5) for strip in range(1, 5) for suffix in ("", "_cal")
            ],
            "tsum_spectra": [
                f"p{plane}_s{strip}_tsum{suffix}"
                for plane in range(1, 5) for strip in range(1, 5) for suffix in ("", "_cal")
            ],
            "charge_spectra": [
                f"p{plane}_s{strip}_{component}{suffix}"
                for plane in range(1, 5) for strip in range(1, 5)
                for component in ("qf", "qb", "qsum", "qdif")
                for suffix in ("", "_cal")
            ],
            "cross_plane_delta_tsum": delta_columns,
        }
        fig_index = 1
        if bool(config.get("create_plots", True)):
            for alias in PLOT_ALIASES:
                if alias not in aliases:
                    continue
                if alias == "charge_spectra_selftrigger_one_plane_topologies":
                    continue
                columns = [column for column in plot_groups[alias] if column in working_df.columns]
                if not columns:
                    continue
                fig_index = plot_debug_histograms(
                    working_df,
                    columns,
                    thresholds=None,
                    title=f"{TASK_NAME} {alias.replace('_', ' ')}: {processing_path.name}",
                    out_dir=str(plot_dir),
                    fig_idx=fig_index,
                    max_cols_per_fig=12,
                    y_scale="log",
                    exclude_zeros=True,
                )
            comparison_alias = "charge_spectra_selftrigger_one_plane_topologies"
            if comparison_alias in aliases:
                comparison_path = _plot_selftrigger_tt_charge_comparison(
                    working_df,
                    raw_tt_codes,
                    raw_active_by_plane,
                    raw_qsum_by_plane,
                    station=station,
                    basename=basename,
                    out_dir=plot_dir,
                    fig_index=fig_index,
                )
                print(
                    "[selftrigger-charge-population-comparison] saved "
                    f"{comparison_path} from this self-trigger parquet"
                )
            saved_plots = sorted(plot_dir.glob("*.png"))
        plot_seconds = time.perf_counter() - plot_start
        update_status_progress(status_path, basename, execution_id, 0.70)

        temp_output = output_path.with_suffix(".parquet.tmp")
        write_start = time.perf_counter()
        working_df.to_parquet(temp_output, engine="pyarrow", compression="zstd", index=False)
        temp_output.replace(output_path)
        write_seconds = time.perf_counter() - write_start
        completed_path = directories["completed"] / processing_path.name
        _move(processing_path, completed_path)

        rate_metadata = build_events_per_second_metadata(working_df)
        denominator = int(rate_metadata.get("events_per_second_total_seconds", 0) or 0)
        add_normalized_count_metadata(rate_metadata, denominator, log_fn=lambda *_: None)
        prune_redundant_count_metadata(rate_metadata, log_fn=lambda *_: None)
        param_value = working_df["param_hash"].iloc[0] if "param_hash" in working_df and len(working_df) else ""
        param_hash = "" if pd.isna(param_value) else str(param_value)
        common = {
            "filename_base": basename,
            "execution_timestamp": execution_id,
            "param_hash": param_hash,
            "station": station,
        }
        data_time = _data_time_metadata(working_df)
        replacing = force_replacement or complete_reanalysis
        save_metadata(
            directories["metadata"] / "task_2_metadata_execution.csv",
            {
                **common,
                "input_filename": completed_path.name,
                "input_rows": int(len(working_df)),
                "input_columns": int(len(working_df.columns)),
                "output_path": str(output_path),
                "output_rows": int(len(working_df)),
                "output_columns": int(len(working_df.columns)),
                "plot_count": len(saved_plots),
                "filtering_enabled": bool(filter_config.get("enabled", True)),
                "charge_values_zeroed": filter_metrics["charge_values_zeroed"],
                "time_values_zeroed": filter_metrics["time_values_zeroed"],
                "calibration_config": calibration_file.name,
                "execution_time_minutes": round((time.perf_counter() - start) / 60.0, 4),
                **data_time,
            },
            replace_existing_basename=replacing,
        )
        specific = {
            **common,
            "event_rows": int(len(working_df)),
            "column_count": int(len(working_df.columns)),
            "plot_count": len(saved_plots),
            "filter_charge_values_zeroed": filter_metrics["charge_values_zeroed"],
            "filter_time_values_zeroed": filter_metrics["time_values_zeroed"],
            "calibration_tdif_matrix": json.dumps(matrices["tdif"].tolist()),
            "calibration_tsum_matrix": json.dumps(matrices["tsum"].tolist()),
            "calibration_qf_matrix": json.dumps(matrices["qf"].tolist()),
            "calibration_qb_matrix": json.dumps(matrices["qb"].tolist()),
            "cross_plane_delta_tsum_pair_count": len(delta_columns),
            **data_time,
        }
        save_metadata(directories["metadata"] / "task_2_metadata_specific.csv", specific, replace_existing_basename=replacing)
        save_metadata(
            directories["metadata"] / "task_2_metadata_rate_histogram.csv",
            {**common, **rate_metadata},
            replace_existing_basename=replacing,
        )
        save_metadata(
            directories["metadata"] / "task_2_metadata_trigger_type.csv",
            {**common, **_trigger_metadata(working_df, basename, execution_id)},
            replace_existing_basename=replacing,
        )
        save_metadata(
            directories["metadata"] / "task_2_metadata_profiling.csv",
            {
                **common,
                "data_read_seconds": round(read_seconds, 4),
                "plot_generation_seconds": round(plot_seconds, 4),
                "parquet_write_seconds": round(write_seconds, 4),
                "total_execution_seconds": round(time.perf_counter() - start, 4),
            },
            replace_existing_basename=replacing,
        )
        update_status_progress(status_path, basename, execution_id, 1.0)
        print(f"Self-trigger Task 2 complete: {output_path} ({len(working_df)} rows)")
        print(f"Input archived: {completed_path}")
        print(f"Runtime PNGs: {plot_dir if saved_plots else 'none generated'}")
        return 0
    except Exception:
        update_status_progress(status_path, basename, execution_id, -1.0)
        if processing_path.exists():
            error_path = directories["error"] / processing_path.name
            if not error_path.exists():
                _move(processing_path, error_path)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply configured Task 2 calibrations to self-trigger events.")
    parser.add_argument("station", type=int, choices=range(5), help="Station number 0-4")
    parser.add_argument("input_file", nargs="?", help="Optional selftrigger_cleaned parquet path")
    parser.add_argument("--input-file", dest="input_file_flag", help="Optional selftrigger_cleaned parquet path")
    parser.add_argument("--verbose", action="store_true", help="Enable detailed processing logs")
    args = parser.parse_args()
    if args.input_file and args.input_file_flag:
        parser.error("Use either positional input_file or --input-file, not both")
    process_one(args.station, args.input_file_flag or args.input_file, verbose=args.verbose)


if __name__ == "__main__":
    main()
