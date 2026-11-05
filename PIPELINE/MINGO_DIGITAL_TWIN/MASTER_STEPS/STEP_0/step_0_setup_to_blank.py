#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_DIGITAL_TWIN/MASTER_STEPS/STEP_0/step_0_setup_to_blank.py
Purpose: STEP_0: append one parameter row with sampled z positions.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_DIGITAL_TWIN/MASTER_STEPS/STEP_0/step_0_setup_to_blank.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

import argparse
from itertools import product
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = ROOT_DIR.parent
sys.path.append(str(ROOT_DIR))
sys.path.append(str(ROOT_DIR / "MASTER_STEPS"))
sys.path.append(str(REPO_ROOT))

from STEP_SHARED.sim_utils import (
    ensure_dir,
    list_station_config_files,
    load_step_configs,
    now_iso,
    param_mesh_lock,
    read_station_config,
    write_csv_atomic,
    write_text_atomic,
)
from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.selection_config import (
    SelectionConfig,
    effective_date_ranges_for_station,
    load_master_selection,
)


def _max_existing_step1_id(intersteps_dir: Path) -> int:
    step1_dir = intersteps_dir / "STEP_1_TO_2"
    if not step1_dir.exists():
        return 0
    max_id = 0
    for sim_dir in step1_dir.glob("SIM_RUN_*"):
        name = sim_dir.name
        if not name.startswith("SIM_RUN_"):
            continue
        first_token = name[len("SIM_RUN_") :].split("_", 1)[0]
        try:
            max_id = max(max_id, int(float(first_token)))
        except (TypeError, ValueError):
            continue
    return max_id


def _assign_step_ids(mesh: pd.DataFrame, *, intersteps_dir: Path | None = None) -> pd.DataFrame:
    mesh = mesh.copy()
    def _ensure_column(name: str) -> None:
        if name not in mesh.columns:
            mesh[name] = pd.NA
        mesh[name] = mesh[name].astype("string")

    def _parse_step_id(value: object) -> int | None:
        if value is None or pd.isna(value):
            return None
        try:
            return int(str(value))
        except ValueError:
            try:
                return int(float(str(value)))
            except ValueError:
                return None

    def _normalize_step_id_column(col: str) -> None:
        def _format(value: object) -> object:
            parsed = _parse_step_id(value)
            if parsed is None:
                return pd.NA
            return f"{parsed:03d}"
        mesh[col] = mesh[col].apply(_format).astype("string")

    for idx in range(1, 11):
        _ensure_column(f"step_{idx}_id")

    def assign_ids(cols: list[str], id_col: str, seed_min_id: int = 0) -> None:
        existing = {}
        if mesh[id_col].notna().any():
            for _, row in mesh[mesh[id_col].notna()].iterrows():
                key = tuple(row[col] for col in cols)
                parsed = _parse_step_id(row[id_col])
                if parsed is not None:
                    existing.setdefault(key, parsed)
        next_id = max(max(existing.values(), default=0), int(seed_min_id)) + 1
        for i, row in mesh.iterrows():
            if pd.notna(row[id_col]):
                continue
            key = tuple(row[col] for col in cols)
            if key not in existing:
                existing[key] = next_id
                next_id += 1
            mesh.at[i, id_col] = f"{existing[key]:03d}"
        _normalize_step_id_column(id_col)

    seed_step1_id = 0
    if intersteps_dir is not None:
        seed_step1_id = _max_existing_step1_id(intersteps_dir)
    assign_ids(["cos_n", "flux_cm2_min", "n_tracks"], "step_1_id", seed_min_id=seed_step1_id)
    assign_ids(["z_p1", "z_p2", "z_p3", "z_p4"], "step_2_id")
    assign_ids(["eff_p1", "eff_p2", "eff_p3", "eff_p4"], "step_3_id")
    for idx in range(4, 9):
        col = f"step_{idx}_id"
        mesh[col] = mesh[col].fillna("001").astype("string")
        _normalize_step_id_column(col)
    assign_ids(["trigger_c1", "trigger_c2", "trigger_c3", "trigger_c4"], "step_9_id")
    mesh["step_10_id"] = mesh["step_10_id"].fillna("001").astype("string")
    _normalize_step_id_column("step_10_id")
    return mesh


def _sample_range(rng: np.random.Generator, value: object, name: str) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, list) and len(value) == 1:
        return float(value[0])
    if isinstance(value, list) and len(value) == 2:
        lo, hi = float(value[0]), float(value[1])
        return float(rng.uniform(lo, hi))
    raise ValueError(
        f"{name} must be a number, a one-value list [value], "
        "or a 2-value list [min, max]."
    )


def _sample_efficiencies(
    rng: np.random.Generator,
    eff_range: object,
    efficiencies_identical: bool,
    efficiencies_max_spread: float | None,
) -> list[float]:
    eff_base = _sample_range(rng, eff_range, "efficiencies")
    if efficiencies_identical:
        return [eff_base] * 4
    if not isinstance(eff_range, list) or len(eff_range) != 2:
        raise ValueError("efficiencies must be a 2-value list [min, max] when not identical.")
    min_val, max_val = float(eff_range[0]), float(eff_range[1])
    if efficiencies_max_spread is None:
        return [float(rng.uniform(min_val, max_val)) for _ in range(4)]
    half_spread = float(efficiencies_max_spread) / 2.0
    lo = max(min_val, eff_base - half_spread)
    hi = min(max_val, eff_base + half_spread)
    return [float(rng.uniform(lo, hi)) for _ in range(4)]


def _as_bool(value: object, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, np.integer)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
    raise ValueError(f"Cannot parse boolean value from {value!r}.")


def _load_event_limit_lookup(physics_cfg: dict) -> tuple[pd.DataFrame, int]:
    fallback = int(physics_cfg.get("event_limits_fallback_n_tracks", 11_250_000))
    configured_path = physics_cfg.get("event_limits_by_min_efficiency")
    if not configured_path:
        return pd.DataFrame(), fallback
    lookup_path = Path(str(configured_path))
    if not lookup_path.is_absolute():
        lookup_path = Path(__file__).resolve().parent / lookup_path
    if not lookup_path.is_file():
        print(
            f"Warning: event-limit lookup not found: {lookup_path}; "
            f"using fallback n_tracks={fallback}."
        )
        return pd.DataFrame(), fallback
    lookup = pd.read_csv(lookup_path)
    required = {
        "min_efficiency_lower",
        "min_efficiency_upper",
        "recommended_n_tracks",
    }
    missing = required - set(lookup.columns)
    if missing:
        raise ValueError(
            f"Event-limit lookup {lookup_path} is missing columns: {sorted(missing)}"
        )
    for column in required:
        lookup[column] = pd.to_numeric(lookup[column], errors="coerce")
    lookup = lookup.dropna(subset=list(required)).sort_values("min_efficiency_lower")
    return lookup, fallback


def _n_tracks_for_efficiencies(
    efficiencies: list[float],
    lookup: pd.DataFrame,
    fallback: int,
) -> int:
    minimum = float(min(efficiencies))
    if lookup.empty:
        return fallback
    matching = lookup.loc[
        (lookup["min_efficiency_lower"] <= minimum)
        & (minimum < lookup["min_efficiency_upper"])
    ]
    if matching.empty:
        distance = (
            ((lookup["min_efficiency_lower"] + lookup["min_efficiency_upper"]) / 2.0)
            - minimum
        ).abs()
        matching = lookup.loc[[distance.idxmin()]]
    return int(matching.iloc[0]["recommended_n_tracks"])


def _range_bounds(value: object, name: str) -> tuple[float, float]:
    if isinstance(value, (int, float)):
        val = float(value)
        return val, val
    if isinstance(value, list) and len(value) == 2:
        lo, hi = float(value[0]), float(value[1])
        if lo > hi:
            raise ValueError(f"{name} range must satisfy min <= max.")
        return lo, hi
    raise ValueError(f"{name} must be a number or a 2-value list [min, max].")


def _parse_efficiency_max_spread(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            parsed = float(value.strip())
        except ValueError as exc:
            raise ValueError(
                "efficiencies_max_spread must be a non-negative number or null."
            ) from exc
    elif isinstance(value, (int, float, np.integer, np.floating)):
        parsed = float(value)
    else:
        raise ValueError(
            "efficiencies_max_spread must be a non-negative number or null."
        )
    if not np.isfinite(parsed):
        raise ValueError("efficiencies_max_spread must be finite or null.")
    if parsed < 0:
        raise ValueError("efficiencies_max_spread must be >= 0.")
    return parsed


def _build_regular_mesh_overrides(
    rng: np.random.Generator,
    physics_cfg: dict,
    eff_range: object,
    efficiencies_identical: bool,
) -> list[dict[str, float]]:
    raw_params = physics_cfg.get("regular_mesh_parameters", physics_cfg.get("mesh_parameters"))
    if isinstance(raw_params, str):
        raw_params = [raw_params]
    if not raw_params:
        raise ValueError(
            "regular_mesh mode requires regular_mesh_parameters (or mesh_parameters)."
        )

    aliases = {
        "flux": "flux_cm2_min",
        "eff": "efficiencies",
        "efficiency": "efficiencies",
    }
    valid = {"cos_n", "flux_cm2_min", "efficiencies"}
    mesh_params: list[str] = []
    for param in raw_params:
        key = aliases.get(str(param).strip().lower(), str(param).strip().lower())
        if key not in valid:
            allowed = ", ".join(sorted(valid))
            raise ValueError(
                f"Unsupported regular mesh parameter '{param}'. Allowed: {allowed}."
            )
        if key not in mesh_params:
            mesh_params.append(key)

    if "efficiencies" in mesh_params and not efficiencies_identical:
        raise ValueError(
            "regular_mesh for efficiencies requires efficiencies_identical=true."
        )

    points = int(physics_cfg.get("regular_mesh_points", physics_cfg.get("mesh_points", 10)))
    if points <= 0:
        raise ValueError("regular_mesh_points must be >= 1.")
    relative_span_cfg = physics_cfg.get(
        "regular_mesh_relative_span", physics_cfg.get("mesh_relative_span")
    )
    if relative_span_cfg is None:
        relative_span = None
    else:
        relative_span = float(relative_span_cfg)
        if relative_span < 0:
            raise ValueError("regular_mesh_relative_span must be >= 0.")

    axes: dict[str, list[float]] = {}
    for param in mesh_params:
        if param == "cos_n":
            lo, hi = _range_bounds(physics_cfg.get("cos_n"), "cos_n")
        elif param == "flux_cm2_min":
            lo, hi = _range_bounds(physics_cfg.get("flux_cm2_min"), "flux_cm2_min")
        else:
            lo, hi = _range_bounds(eff_range, "efficiencies")

        if points == 1 or lo == hi:
            center = lo if lo == hi else float(rng.uniform(lo, hi))
            values = np.array([center], dtype=float)
        else:
            width = hi - lo
            max_span = (points - 1) / (2 * points)
            span = max_span if relative_span is None else min(relative_span, max_span)
            half_span = span * width
            center_lo = lo + half_span
            center_hi = hi - half_span
            center = center_lo if center_hi <= center_lo else float(rng.uniform(center_lo, center_hi))
            values = np.linspace(center - half_span, center + half_span, num=points, dtype=float)
        values = np.round(values.astype(float), 10)
        axes[param] = [float(v) for v in values]

    overrides: list[dict[str, float]] = []
    for combo in product(*(axes[param] for param in mesh_params)):
        row_override: dict[str, float] = {}
        for param, value in zip(mesh_params, combo):
            if param == "efficiencies":
                row_override["eff_p1"] = float(value)
                row_override["eff_p2"] = float(value)
                row_override["eff_p3"] = float(value)
                row_override["eff_p4"] = float(value)
            else:
                row_override[param] = float(value)
        overrides.append(row_override)
    return overrides


def _date_range_overlap_mask(
    frame: pd.DataFrame,
    date_ranges: Iterable[tuple[datetime | None, datetime | None]] | None,
) -> pd.Series:
    if not date_ranges:
        return pd.Series(True, index=frame.index)

    if "start" not in frame.columns or "end" not in frame.columns:
        return pd.Series(True, index=frame.index)

    start_day = pd.to_datetime(frame["start"], errors="coerce").dt.normalize()
    end_day = pd.to_datetime(frame["end"], errors="coerce").dt.normalize()
    far_future = pd.Timestamp("2262-04-11")
    end_day = end_day.fillna(far_future)

    mask = pd.Series(False, index=frame.index)
    for start_value, end_value in date_ranges:
        range_start = (
            pd.Timestamp(start_value).normalize()
            if start_value is not None
            else pd.Timestamp("1900-01-01")
        )
        range_end = (
            pd.Timestamp(end_value).normalize()
            if end_value is not None
            else far_future
        )
        mask |= (start_day <= range_end) & (end_day >= range_start)
    return mask.fillna(False)


def _selected_station_ids_for_z_adaptation(
    station_files: dict[int, Path],
    selection: SelectionConfig,
) -> list[int]:
    available_real = sorted(station_id for station_id in station_files if station_id != 0)
    if selection.stations is None:
        return available_real

    selected_real = sorted(
        station_id
        for station_id in selection.stations
        if station_id in station_files and station_id != 0
    )
    return selected_real or available_real


def _effective_step0_date_ranges(
    station_id: int,
    *,
    selection: SelectionConfig | None = None,
    date_ranges: Iterable[tuple[datetime | None, datetime | None]] | None = None,
) -> tuple[tuple[datetime | None, datetime | None], ...] | None:
    if selection is not None:
        return effective_date_ranges_for_station(station_id, selection)
    if date_ranges is None:
        return None
    return tuple(date_ranges)


def _collect_z_positions(
    station_files: dict[int, Path],
    *,
    selected_station_ids: Iterable[int] | None = None,
    selection: SelectionConfig | None = None,
    date_ranges: Iterable[tuple[datetime | None, datetime | None]] | None = None,
) -> pd.DataFrame:
    if selected_station_ids is None:
        selected_ids = sorted(station_files)
    else:
        selected_ids = [station_id for station_id in selected_station_ids if station_id in station_files]
    station_dfs: list[pd.DataFrame] = []
    for station_id in selected_ids:
        df = read_station_config(station_files[station_id]).copy()
        df["station"] = station_id
        station_ranges = _effective_step0_date_ranges(
            station_id,
            selection=selection,
            date_ranges=date_ranges,
        )
        mask = _date_range_overlap_mask(df, station_ranges)
        filtered = df.loc[mask].copy()
        if not filtered.empty:
            station_dfs.append(filtered)
    if not station_dfs:
        return pd.DataFrame(columns=["P1", "P2", "P3", "P4"])
    geom_cols = ["P1", "P2", "P3", "P4"]
    all_geoms = pd.concat([df[geom_cols] for df in station_dfs], ignore_index=True)
    unique_geoms = all_geoms.dropna().drop_duplicates().reset_index(drop=True)
    non_zero = (unique_geoms[geom_cols] != 0).any(axis=1)
    unique_geoms = unique_geoms[non_zero].reset_index(drop=True)
    return unique_geoms


def _collect_geometry_trigger_rows(
    station_files: dict[int, Path],
    *,
    selected_station_ids: Iterable[int] | None = None,
    selection: SelectionConfig | None = None,
    date_ranges: Iterable[tuple[datetime | None, datetime | None]] | None = None,
) -> pd.DataFrame:
    if selected_station_ids is None:
        selected_ids = sorted(station_files)
    else:
        selected_ids = [station_id for station_id in selected_station_ids if station_id in station_files]
    station_dfs: list[pd.DataFrame] = []
    for station_id in selected_ids:
        df = read_station_config(station_files[station_id]).copy()
        df["station"] = station_id
        station_ranges = _effective_step0_date_ranges(
            station_id,
            selection=selection,
            date_ranges=date_ranges,
        )
        mask = _date_range_overlap_mask(df, station_ranges)
        filtered = df.loc[mask].copy()
        if not filtered.empty:
            station_dfs.append(filtered)
    if not station_dfs:
        return pd.DataFrame(columns=["P1", "P2", "P3", "P4", "C1", "C2", "C3", "C4"])
    cols = ["P1", "P2", "P3", "P4", "C1", "C2", "C3", "C4"]
    combined = pd.concat([df[cols] for df in station_dfs], ignore_index=True)
    combined = combined.dropna().drop_duplicates().reset_index(drop=True)
    geom_non_zero = (combined[["P1", "P2", "P3", "P4"]] != 0).any(axis=1)
    combined = combined[geom_non_zero].reset_index(drop=True)
    return combined


def _z_positions_from_override(raw_override: object) -> pd.DataFrame:
    if raw_override is None:
        return pd.DataFrame(columns=["P1", "P2", "P3", "P4"])
    if not isinstance(raw_override, list) or not raw_override:
        raise ValueError(
            "z_positions_override_mm must be a list with 4 values "
            "or a list of 4-value lists."
        )

    def _parse_tuple(values: object) -> list[float]:
        if not isinstance(values, list) or len(values) != 4:
            raise ValueError(
                "Each z_positions_override_mm entry must contain exactly 4 values [P1, P2, P3, P4]."
            )
        return [float(values[0]), float(values[1]), float(values[2]), float(values[3])]

    rows: list[list[float]] = []
    first = raw_override[0]
    if isinstance(first, list):
        for entry in raw_override:
            rows.append(_parse_tuple(entry))
    else:
        if len(raw_override) != 4:
            raise ValueError(
                "z_positions_override_mm must have exactly 4 values when using a single geometry."
            )
        rows.append(_parse_tuple(raw_override))

    override_df = pd.DataFrame(rows, columns=["P1", "P2", "P3", "P4"])
    override_df = override_df.dropna().drop_duplicates().reset_index(drop=True)
    if override_df.empty:
        raise ValueError("z_positions_override_mm produced no valid geometry rows.")
    return override_df


def _expected_counts_from_mesh(mesh: pd.DataFrame, include_done: bool) -> dict[str, int]:
    if "done" in mesh.columns and not include_done:
        mesh = mesh[mesh["done"].fillna(0).astype(int) != 1]
    step1 = mesh["step_1_id"].astype(str).nunique() if "step_1_id" in mesh.columns else 0
    step2 = mesh["step_2_id"].astype(str).nunique() if "step_2_id" in mesh.columns else 0
    step3 = mesh["step_3_id"].astype(str).nunique() if "step_3_id" in mesh.columns else 0
    counts = {
        "STEP_1_TO_2": step1,
        "STEP_2_TO_3": step1 * step2,
        "STEP_3_TO_4": step1 * step2 * step3,
    }
    total = counts["STEP_3_TO_4"]
    for step in range(4, 11):
        counts[f"STEP_{step}_TO_{step + 1}"] = total
    return counts


def _total_generation_pct(intersteps_dir: Path, mesh: pd.DataFrame) -> tuple[float, int, int]:
    expected = _expected_counts_from_mesh(mesh, include_done=True)
    step_dirs = sorted(intersteps_dir.glob("STEP_*_TO_*"))
    total_dirs = 0
    total_expected_dirs = 0
    for step_dir in step_dirs:
        step_name = step_dir.name
        if "0_TO_1" in step_name or "10_TO_FINAL" in step_name:
            continue
        total_dirs += len(list(step_dir.glob("SIM_RUN_*")))
        total_expected_dirs += expected.get(step_name, 0)
    if total_expected_dirs == 0:
        total_pct = 0.0 if not mesh.empty else 100.0
    else:
        total_pct = total_dirs / total_expected_dirs * 100.0
    return total_pct, total_dirs, total_expected_dirs


def _append_param_row(
    mesh_path: Path,
    meta_path: Path,
    physics_cfg: dict,
    rng: np.random.Generator,
    geometry_rows: pd.DataFrame,
) -> None:
    mode = str(physics_cfg.get("mode", "uniform_random")).strip().lower()
    if mode not in {"uniform_random", "regular_mesh"}:
        raise ValueError("mode must be either 'uniform_random' or 'regular_mesh'.")

    efficiencies_identical = _as_bool(
        physics_cfg.get("efficiencies_identical", False), default=False
    )
    efficiencies_max_spread = _parse_efficiency_max_spread(
        physics_cfg.get("efficiencies_max_spread", 0.10)
    )
    eff_range = physics_cfg.get("efficiencies")
    if eff_range is None:
        raise ValueError("efficiencies must be set in config_step_0_physics.yaml.")
    event_limit_lookup, fallback_n_tracks = _load_event_limit_lookup(physics_cfg)
    repeat_samples = int(physics_cfg.get("repeat_samples", 0))
    if repeat_samples < 0:
        raise ValueError("repeat_samples must be >= 0 (0 = one sample per geometry, no repeats).")
    shared_columns = physics_cfg.get("shared_columns", [])
    if isinstance(shared_columns, str):
        shared_columns = [shared_columns]
    shared = {str(col) for col in shared_columns or []}
    if "efficiencies" in shared:
        shared.update({"eff_p1", "eff_p2", "eff_p3", "eff_p4"})
    if "z_positions" in shared:
        shared.update({"z_p1", "z_p2", "z_p3", "z_p4"})

    if mesh_path.exists():
        try:
            mesh = pd.read_csv(mesh_path)
        except pd.errors.EmptyDataError:
            mesh = pd.DataFrame()
        if "done" not in mesh.columns:
            mesh["done"] = 0
        dup_cols = [col for col in mesh.columns if col.endswith(".1")]
        for col in dup_cols:
            base = col[:-2]
            if base in mesh.columns:
                mesh = mesh.drop(columns=[col])
        if mesh.columns.duplicated().any():
            mesh = mesh.loc[:, ~mesh.columns.duplicated()]
    else:
        mesh = pd.DataFrame()
        mesh["done"] = []
    if "n_tracks" not in mesh.columns:
        mesh["n_tracks"] = fallback_n_tracks
    else:
        mesh["n_tracks"] = (
            pd.to_numeric(mesh["n_tracks"], errors="coerce")
            .fillna(fallback_n_tracks)
            .astype(int)
        )
    if "param_set_id" not in mesh.columns:
        mesh["param_set_id"] = pd.NA
    if "param_date" not in mesh.columns:
        mesh["param_date"] = pd.NA
    if "execution_time" not in mesh.columns:
        mesh["execution_time"] = now_iso()
    else:
        missing_et = mesh["execution_time"].isna()
        if missing_et.any():
            mesh.loc[missing_et, "execution_time"] = now_iso()
    mesh["done"] = mesh["done"].fillna(0).astype(int)

    if geometry_rows.empty:
        raise ValueError("No geometry/trigger rows found in station configs; cannot build param mesh.")

    z_positions = geometry_rows[["P1", "P2", "P3", "P4"]].drop_duplicates().reset_index(drop=True)

    for col in ("z_p1", "z_p2", "z_p3", "z_p4"):
        if col not in mesh.columns:
            mesh[col] = np.nan
    for col in ("trigger_c1", "trigger_c2", "trigger_c3", "trigger_c4"):
        if col not in mesh.columns:
            mesh[col] = pd.NA

    if not mesh.empty:
        missing_mask = mesh[
            ["z_p1", "z_p2", "z_p3", "z_p4", "trigger_c1", "trigger_c2", "trigger_c3", "trigger_c4"]
        ].isna().any(axis=1)
        if missing_mask.any():
            for idx in mesh.index[missing_mask]:
                row_geom = mesh.loc[idx, ["z_p1", "z_p2", "z_p3", "z_p4"]]
                has_geom = not row_geom.isna().any()
                if has_geom:
                    geom_frame = geometry_rows[
                        np.isclose(pd.to_numeric(geometry_rows["P1"], errors="coerce"), float(row_geom["z_p1"]), atol=1e-6)
                        & np.isclose(pd.to_numeric(geometry_rows["P2"], errors="coerce"), float(row_geom["z_p2"]), atol=1e-6)
                        & np.isclose(pd.to_numeric(geometry_rows["P3"], errors="coerce"), float(row_geom["z_p3"]), atol=1e-6)
                        & np.isclose(pd.to_numeric(geometry_rows["P4"], errors="coerce"), float(row_geom["z_p4"]), atol=1e-6)
                    ]
                else:
                    geom_frame = geometry_rows
                if geom_frame.empty:
                    geom_frame = geometry_rows
                geom_row = geom_frame.sample(
                    n=1, random_state=rng.integers(0, 2**32 - 1)
                ).iloc[0]
                if pd.isna(mesh.at[idx, "z_p1"]):
                    mesh.at[idx, "z_p1"] = float(geom_row["P1"])
                if pd.isna(mesh.at[idx, "z_p2"]):
                    mesh.at[idx, "z_p2"] = float(geom_row["P2"])
                if pd.isna(mesh.at[idx, "z_p3"]):
                    mesh.at[idx, "z_p3"] = float(geom_row["P3"])
                if pd.isna(mesh.at[idx, "z_p4"]):
                    mesh.at[idx, "z_p4"] = float(geom_row["P4"])
                if pd.isna(mesh.at[idx, "trigger_c1"]):
                    mesh.at[idx, "trigger_c1"] = str(geom_row["C1"]).strip()
                if pd.isna(mesh.at[idx, "trigger_c2"]):
                    mesh.at[idx, "trigger_c2"] = str(geom_row["C2"]).strip()
                if pd.isna(mesh.at[idx, "trigger_c3"]):
                    mesh.at[idx, "trigger_c3"] = str(geom_row["C3"]).strip()
                if pd.isna(mesh.at[idx, "trigger_c4"]):
                    mesh.at[idx, "trigger_c4"] = str(geom_row["C4"]).strip()

    shared_values: dict[str, float] = {}
    expand_z_positions = _as_bool(physics_cfg.get("expand_z_positions", False), default=False)
    shared_geom_row = None
    if not expand_z_positions and {"z_p1", "z_p2", "z_p3", "z_p4"} & shared:
        shared_geom_row = geometry_rows.sample(
            n=1, random_state=rng.integers(0, 2**32 - 1)
        ).iloc[0]
        shared_values.update(
            {
                "z_p1": float(shared_geom_row["P1"]),
                "z_p2": float(shared_geom_row["P2"]),
                "z_p3": float(shared_geom_row["P3"]),
                "z_p4": float(shared_geom_row["P4"]),
            }
        )
    if "cos_n" in shared:
        shared_values["cos_n"] = _sample_range(rng, physics_cfg.get("cos_n"), "cos_n")
    if "flux_cm2_min" in shared:
        shared_values["flux_cm2_min"] = _sample_range(
            rng, physics_cfg.get("flux_cm2_min"), "flux_cm2_min"
        )
    if {"eff_p1", "eff_p2", "eff_p3", "eff_p4"} & shared:
        effs_shared = _sample_efficiencies(
            rng,
            eff_range,
            efficiencies_identical,
            efficiencies_max_spread,
        )
        shared_values.update(
            {
                "eff_p1": float(effs_shared[0]),
                "eff_p2": float(effs_shared[1]),
                "eff_p3": float(effs_shared[2]),
                "eff_p4": float(effs_shared[3]),
            }
        )

    new_rows = []
    row_creation_ts = now_iso()
    if mode == "regular_mesh":
        # Build one structured grid per invocation; repeat_samples remains for uniform_random mode.
        sample_overrides: list[dict[str, float] | None] = _build_regular_mesh_overrides(
            rng=rng,
            physics_cfg=physics_cfg,
            eff_range=eff_range,
            efficiencies_identical=efficiencies_identical,
        )
    else:
        n_samples = repeat_samples + 1  # 0 repeats → 1 base sample; N repeats → N+1
        sample_overrides = [None] * n_samples

    for override in sample_overrides:
        cos_n = shared_values.get("cos_n", _sample_range(rng, physics_cfg.get("cos_n"), "cos_n"))
        flux_cm2_min = shared_values.get(
            "flux_cm2_min", _sample_range(rng, physics_cfg.get("flux_cm2_min"), "flux_cm2_min")
        )
        effs = _sample_efficiencies(
            rng,
            eff_range,
            efficiencies_identical,
            efficiencies_max_spread,
        )
        for key in ("eff_p1", "eff_p2", "eff_p3", "eff_p4"):
            if key in shared_values:
                idx = int(key.split("_p")[-1]) - 1
                effs[idx] = float(shared_values[key])
        if override:
            if "cos_n" in override:
                cos_n = float(override["cos_n"])
            if "flux_cm2_min" in override:
                flux_cm2_min = float(override["flux_cm2_min"])
            for key in ("eff_p1", "eff_p2", "eff_p3", "eff_p4"):
                if key in override:
                    idx = int(key.split("_p")[-1]) - 1
                    effs[idx] = float(override[key])
        if shared_geom_row is not None:
            geom_rows = [shared_geom_row]
        elif expand_z_positions:
            geom_rows = [row for _, row in geometry_rows.iterrows()]
        else:
            geom_rows = [
                geometry_rows.sample(n=1, random_state=rng.integers(0, 2**32 - 1)).iloc[0]
            ]
        for geom_row in geom_rows:
            new_rows.append(
                {
                    "done": 0,
                    "execution_time": row_creation_ts,
                    "cos_n": float(cos_n),
                    "flux_cm2_min": float(flux_cm2_min),
                    "z_p1": float(geom_row["P1"]),
                    "z_p2": float(geom_row["P2"]),
                    "z_p3": float(geom_row["P3"]),
                    "z_p4": float(geom_row["P4"]),
                    "trigger_c1": str(geom_row["C1"]).strip(),
                    "trigger_c2": str(geom_row["C2"]).strip(),
                    "trigger_c3": str(geom_row["C3"]).strip(),
                    "trigger_c4": str(geom_row["C4"]).strip(),
                    "eff_p1": float(effs[0]),
                    "eff_p2": float(effs[1]),
                    "eff_p3": float(effs[2]),
                    "eff_p4": float(effs[3]),
                    "n_tracks": _n_tracks_for_efficiencies(
                        [float(value) for value in effs],
                        event_limit_lookup,
                        fallback_n_tracks,
                    ),
                }
            )
    new_rows_df = pd.DataFrame(new_rows)
    for col in mesh.columns:
        if col not in new_rows_df.columns:
            new_rows_df[col] = pd.NA
    for col in new_rows_df.columns:
        if col not in mesh.columns:
            mesh[col] = pd.NA
    new_rows_df = new_rows_df[mesh.columns]
    if mesh.empty:
        mesh = new_rows_df.copy()
    else:
        mesh = pd.concat([mesh, new_rows_df], ignore_index=True)
    mesh = _assign_step_ids(mesh, intersteps_dir=mesh_path.parent.parent)
    if "param_set_id" in mesh.columns:
        mesh = mesh.sort_values("param_set_id").reset_index(drop=True)
    z_cols = ["z_p1", "z_p2", "z_p3", "z_p4"]
    head_cols = ["done", "param_set_id", "param_date", "execution_time"]
    step_id_cols = [f"step_{idx}_id" for idx in range(1, 11)]
    trigger_cols = ["trigger_c1", "trigger_c2", "trigger_c3", "trigger_c4"]
    front_cols = ["cos_n", "flux_cm2_min", "n_tracks"] + z_cols + trigger_cols
    ordered_cols = (
        [c for c in head_cols if c in mesh.columns]
        + [c for c in step_id_cols if c in mesh.columns]
        + [c for c in front_cols if c in mesh.columns]
        + [
            c
            for c in mesh.columns
            if c not in head_cols and c not in front_cols and c not in step_id_cols
        ]
    )
    mesh = mesh[ordered_cols]
    mesh["done"] = mesh["done"].fillna(0).astype(int)
    write_csv_atomic(mesh, mesh_path, index=False)

    meta = {
        "updated_at": now_iso(),
        "row_count": int(len(mesh)),
        "efficiencies_identical": efficiencies_identical,
        "efficiencies_max_spread": efficiencies_max_spread,
        "repeat_samples": repeat_samples,
        "expand_z_positions": expand_z_positions,
        "shared_columns": sorted(shared),
        "mode": mode,
        "step": "STEP_0",
    }
    write_text_atomic(meta_path, json.dumps(meta, indent=2))


def _log_info(message: str) -> None:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [STEP_0] {message}")


def main() -> None:
    parser = argparse.ArgumentParser(description="STEP_0: append one parameter row and update mesh.")
    parser.add_argument(
        "--config",
        default="config_step_0_physics.yaml",
        help="Path to step physics config YAML",
    )
    parser.add_argument(
        "--runtime-config",
        default=None,
        help="Path to step runtime config YAML (defaults to *_runtime.yaml)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Append even if total completion is below 100%%.",
    )
    args = parser.parse_args()

    _log_info("STEP_0 setup started")

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = Path(__file__).resolve().parent / config_path
    runtime_path = Path(args.runtime_config) if args.runtime_config else None
    if runtime_path is not None and not runtime_path.is_absolute():
        runtime_path = Path(__file__).resolve().parent / runtime_path

    physics_cfg, runtime_cfg, cfg, runtime_path = load_step_configs(config_path, runtime_path)
    force_from_cfg = _as_bool(cfg.get("force", False), default=False)
    force_append = args.force or force_from_cfg

    _log_info(
        "Loaded configs: "
        f"physics={config_path}, "
        f"runtime={runtime_path if runtime_path else 'auto'}"
    )

    default_station_root = (
        Path(__file__).resolve().parents[3]
        / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_SCRIPTS"
        / "CONFIG_FILES"
        / "STAGE_0"
        / "ONLINE_RUN_DICTIONARY"
    )
    station_root = Path(cfg.get("station_config_root", str(default_station_root))).expanduser()
    if not station_root.is_absolute():
        station_root = Path(__file__).resolve().parent / station_root
    if not station_root.exists():
        raise FileNotFoundError(f"station_config_root not found: {station_root}")

    output_dir = Path(cfg.get("output_dir", "../../SIMULATION_OUTPUTS/INTERSTEPS/STEP_0_TO_1"))
    if not output_dir.is_absolute():
        output_dir = Path(__file__).resolve().parent / output_dir
    ensure_dir(output_dir)
    _log_info(f"Output directory: {output_dir}")

    station_files = list_station_config_files(station_root)
    if not station_files:
        raise FileNotFoundError(f"No station config CSVs found under {station_root}")
    _log_info(f"Station configs found: {len(station_files)}")

    adapt_z_positions = _as_bool(
        physics_cfg.get("adapt_z_positions_for_station_date_range", False),
        default=False,
    )
    adapt_trigger_combinations = _as_bool(
        physics_cfg.get("adapt_trigger_combinations_for_station_date_range", False),
        default=False,
    )
    z_override = _z_positions_from_override(physics_cfg.get("z_positions_override_mm"))
    if adapt_z_positions or adapt_trigger_combinations:
        selection = load_master_selection(REPO_ROOT / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_SCRIPTS" / "CONFIG_FILES")
        selected_station_ids = _selected_station_ids_for_z_adaptation(station_files, selection)
        effective_ranges_by_station = {
            station_id: list(_effective_step0_date_ranges(station_id, selection=selection) or ())
            for station_id in selected_station_ids
        }
        if not z_override.empty:
            _log_info(
                "Ignoring z_positions_override_mm because "
                "station/date-range adaptation is enabled for geometry and/or triggers."
            )
        geometry_rows = _collect_geometry_trigger_rows(
            station_files,
            selected_station_ids=selected_station_ids,
            selection=selection,
        )
        if geometry_rows.empty:
            _log_info(
                "No geometry/trigger rows matched the selected stations/date ranges; "
                "falling back to all available station rows for those stations."
            )
            geometry_rows = _collect_geometry_trigger_rows(
                station_files,
                selected_station_ids=selected_station_ids,
                date_ranges=None,
            )
        z_positions = geometry_rows[["P1", "P2", "P3", "P4"]].drop_duplicates().reset_index(drop=True)
        _log_info(
            "Unique geometry/trigger rows (from selected station configs/date ranges): "
            f"{len(geometry_rows)}; unique z rows=f{len(z_positions)}, which are f{z_positions}, stations={selected_station_ids} "
            f"effective_date_ranges={effective_ranges_by_station if any(effective_ranges_by_station.values()) else 'all'}"
        )
    elif z_override.empty:
        z_positions = _collect_z_positions(station_files)
        geometry_rows = z_positions.copy()
        for col, fallback in zip(("C1", "C2", "C3", "C4"), ("12", "23", "34", "13")):
            geometry_rows[col] = fallback
        _log_info(f"Unique z-position rows (from station configs): {len(z_positions)}")
    else:
        z_positions = z_override
        geometry_rows = z_positions.copy()
        for col, fallback in zip(("C1", "C2", "C3", "C4"), ("12", "23", "34", "13")):
            geometry_rows[col] = fallback
        z_rows = "; ".join(
            f"({row.P1:g}, {row.P2:g}, {row.P3:g}, {row.P4:g})"
            for row in z_positions.itertuples(index=False)
        )
        _log_info(
            "Using z-position override from config_step_0_physics.yaml: "
            f"rows={len(z_positions)} values={z_rows}"
        )

    rng = np.random.default_rng(cfg.get("seed"))
    mesh_path = output_dir / "param_mesh.csv"
    mesh_meta_path = output_dir / "param_mesh_metadata.json"

    with param_mesh_lock(mesh_path):
        if mesh_path.exists() and not force_append:
            try:
                mesh = pd.read_csv(mesh_path)
            except pd.errors.EmptyDataError:
                mesh = pd.DataFrame()
            if "done" not in mesh.columns:
                mesh["done"] = 0
            done_series = mesh["done"].fillna(0).astype(int)
            total_rows = len(mesh)
            done_rows = int((done_series == 1).sum())
            if total_rows > 0 and done_rows < total_rows:
                done_pct = done_rows / total_rows * 100.0
                print(
                    "Skipping append: mesh completion "
                    f"{done_pct:.1f}% ({done_rows}/{total_rows} rows done) is below 100%."
                )
                _log_info("Skip append: mesh not fully done")
                return

        _append_param_row(mesh_path, mesh_meta_path, physics_cfg, rng, geometry_rows)

        try:
            mesh = pd.read_csv(mesh_path)
            _log_info(f"Mesh rows after append: {len(mesh)}")
        except (OSError, pd.errors.ParserError, pd.errors.EmptyDataError):
            _log_info("Mesh updated (row count unavailable)")

        meta = {
            "created_at": now_iso(),
            "step": "STEP_0",
            "config": physics_cfg,
            "runtime_config": runtime_cfg,
            "force": force_append,
            "station_config_root": str(station_root),
        }
        write_text_atomic(mesh_meta_path, json.dumps(meta, indent=2))

    _log_info(f"Updated param mesh in {output_dir}")


if __name__ == "__main__":
    main()
