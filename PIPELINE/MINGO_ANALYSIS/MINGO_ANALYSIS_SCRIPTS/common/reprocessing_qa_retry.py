"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/common/reprocessing_qa_retry.py
Purpose: Shared helpers for QA-driven reprocessing retries.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-04-22
Runtime: python3
Usage: python3 -m MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.reprocessing_qa_retry [options]
Inputs: Config files and CSV manifests.
Outputs: QA retry manifests/state CSVs or stdout summaries.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

import argparse
import fcntl
import os
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import yaml

from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.selection_config import parse_station_id
from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.path_config import get_repo_root


MANIFEST_COLUMNS = [
    "basename",
    "target_station",
    "selector_id",
    "qa_station",
    "quality_status",
    "plot_timestamp",
    "failed_quality_columns",
    "failed_quality_versions",
]

STATE_COLUMNS = MANIFEST_COLUMNS + [
    "first_seen_at",
    "last_seen_at",
    "admitted_at",
    "is_active",
]


@dataclass(frozen=True)
class QARetrySelector:
    selector_id: str
    target_stations: tuple[str, ...]
    qa_stations: tuple[str, ...]
    quality_statuses: tuple[str, ...]
    failed_columns_any: tuple[str, ...]


def _station_name(value: Any) -> str:
    station_id = parse_station_id(value)
    if station_id is None:
        raise ValueError(f"Invalid station value '{value}'.")
    return f"MINGO{station_id:02d}"


def _normalize_station_names(value: Any) -> tuple[str, ...]:
    if value in (None, "", []):
        return ()

    raw_values: list[Any]
    if isinstance(value, str):
        raw_values = [token for token in value.replace(";", ",").split(",") if token.strip()]
    elif isinstance(value, (list, tuple, set)):
        raw_values = list(value)
    else:
        raw_values = [value]

    normalized: list[str] = []
    for item in raw_values:
        try:
            normalized.append(_station_name(item))
        except ValueError:
            continue
    return tuple(dict.fromkeys(normalized))


def _ensure_list(value: Any, *, default: list[str] | None = None) -> list[str]:
    if value is None:
        return list(default or [])
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else list(default or [])
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return list(default or [])


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = _deep_merge(existing, value)
        else:
            merged[key] = value
    return merged


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    return loaded if isinstance(loaded, dict) else {}


def _load_qa_retry_config(config_paths: Iterable[Path]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for config_path in config_paths:
        data = _load_yaml_mapping(config_path)
        qa_retry = data.get("qa_retry")
        if isinstance(qa_retry, dict):
            merged = _deep_merge(merged, qa_retry)
    return merged


def _parse_selectors(config: dict[str, Any]) -> list[QARetrySelector]:
    selectors_raw = config.get("selectors")
    if not isinstance(selectors_raw, list):
        return []

    selectors: list[QARetrySelector] = []
    for item in selectors_raw:
        if not isinstance(item, dict):
            continue
        selector_id = str(item.get("id", "")).strip()
        if not selector_id:
            continue

        target_stations = _normalize_station_names(
            item.get("target_stations", item.get("reprocessing_stations"))
        )
        qa_stations = _normalize_station_names(item.get("qa_stations", item.get("qa_station")))
        quality_statuses = tuple(
            value.lower() for value in _ensure_list(item.get("quality_statuses"), default=["fail"])
        )
        failed_columns_any = tuple(_ensure_list(item.get("failed_columns_any"), default=["*"]))

        selectors.append(
            QARetrySelector(
                selector_id=selector_id,
                target_stations=target_stations,
                qa_stations=qa_stations,
                quality_statuses=quality_statuses,
                failed_columns_any=failed_columns_any,
            )
        )
    return selectors


def _csv_lock_path(path: Path) -> Path:
    return path.with_name(f".{path.name}.lock")


@contextmanager
def _locked_csv_transaction(path: Path) -> Iterable[None]:
    lock_path = _csv_lock_path(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _read_csv(path: Path, *, columns: list[str]) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame(columns=columns)
    try:
        df = pd.read_csv(path, keep_default_na=False, dtype=str)
    except pd.errors.ParserError as exc:
        print(
            f"[WARN] Skipping malformed row(s) while reading CSV state from {path}: {exc}",
            file=sys.stderr,
        )
        df = pd.read_csv(
            path,
            keep_default_na=False,
            dtype=str,
            engine="python",
            on_bad_lines="skip",
        )
    for column in columns:
        if column not in df.columns:
            df[column] = ""
    return df[columns].copy()


def _write_csv(path: Path, df: pd.DataFrame, *, columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    for column in columns:
        if column not in df.columns:
            df[column] = ""
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            df[columns].to_csv(handle, index=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink(missing_ok=True)


def _read_clean_basenames(clean_csv: Path) -> list[str]:
    if not clean_csv.exists() or clean_csv.stat().st_size == 0:
        return []
    df = pd.read_csv(clean_csv, keep_default_na=False, dtype=str)
    if "basename" not in df.columns:
        return []
    return [
        value.strip()
        for value in df["basename"].astype(str).tolist()
        if value and value.strip()
    ]


def _failed_columns_match(failed_columns: str, patterns: tuple[str, ...]) -> bool:
    if not patterns:
        return True

    tokens = [token.strip() for token in str(failed_columns).split(";") if token.strip()]
    if not tokens:
        return any(pattern == "*" for pattern in patterns)

    for token in tokens:
        for pattern in patterns:
            if fnmatch(token, pattern):
                return True
    return False


def _current_retry_rows(
    *,
    station_name: str,
    clean_basenames: list[str],
    qa_df: pd.DataFrame,
    selectors: list[QARetrySelector],
) -> pd.DataFrame:
    clean_set = set(clean_basenames)
    records: list[dict[str, str]] = []
    if qa_df.empty or not clean_set:
        return pd.DataFrame(columns=MANIFEST_COLUMNS)

    qa_working = qa_df.copy()
    qa_working["station_name"] = qa_working["station_name"].astype(str).str.strip()
    qa_working["filename_base"] = qa_working["filename_base"].astype(str).str.strip()
    qa_working["quality_status"] = qa_working["quality_status"].astype(str).str.strip().str.lower()
    qa_working["failed_quality_columns"] = qa_working["failed_quality_columns"].astype(str).str.strip()
    if "failed_quality_versions" not in qa_working.columns:
        qa_working["failed_quality_versions"] = ""
    qa_working["failed_quality_versions"] = qa_working["failed_quality_versions"].astype(str).str.strip()
    qa_working["plot_timestamp"] = qa_working["plot_timestamp"].astype(str).str.strip()

    qa_working = qa_working[qa_working["filename_base"].isin(clean_set)].copy()
    if qa_working.empty:
        return pd.DataFrame(columns=MANIFEST_COLUMNS)

    for selector in selectors:
        if selector.target_stations and station_name not in selector.target_stations:
            continue

        selector_df = qa_working.copy()
        if selector.qa_stations:
            selector_df = selector_df[selector_df["station_name"].isin(selector.qa_stations)].copy()
        if selector_df.empty:
            continue

        selector_df = selector_df[selector_df["quality_status"].isin(set(selector.quality_statuses))].copy()
        if selector_df.empty:
            continue

        selector_df = selector_df[
            selector_df["failed_quality_columns"].map(
                lambda value: _failed_columns_match(value, selector.failed_columns_any)
            )
        ].copy()
        if selector_df.empty:
            continue

        for row in selector_df.itertuples(index=False):
            records.append(
                {
                    "basename": row.filename_base,
                    "target_station": station_name,
                    "selector_id": selector.selector_id,
                    "qa_station": row.station_name,
                    "quality_status": row.quality_status,
                    "plot_timestamp": row.plot_timestamp,
                    "failed_quality_columns": row.failed_quality_columns,
                    "failed_quality_versions": row.failed_quality_versions,
                }
            )

    if not records:
        return pd.DataFrame(columns=MANIFEST_COLUMNS)

    out = pd.DataFrame(records)
    out = out.drop_duplicates(subset=["basename", "selector_id"], keep="last")
    return out.sort_values(["basename", "selector_id"]).reset_index(drop=True)


def _state_key(row: pd.Series | dict[str, Any]) -> tuple[str, str]:
    return (str(row["basename"]).strip(), str(row["selector_id"]).strip())


def build_retry_manifest(
    *,
    config_paths: list[Path],
    station: Any,
    clean_csv: Path,
    output_csv: Path,
    state_csv: Path,
    now_timestamp: str,
) -> dict[str, int]:
    station_name = _station_name(station)
    config = _load_qa_retry_config(config_paths)
    enabled = bool(config.get("enabled", False))

    if not enabled:
        with _locked_csv_transaction(state_csv):
            state_df = _read_csv(state_csv, columns=STATE_COLUMNS)
            if not state_df.empty:
                state_df["is_active"] = "0"
                _write_csv(state_csv, state_df, columns=STATE_COLUMNS)
            _write_csv(output_csv, pd.DataFrame(columns=MANIFEST_COLUMNS), columns=MANIFEST_COLUMNS)
            return {"manifest_rows": 0, "state_rows": len(state_df), "active_rows": 0}

    source_csv_raw = str(config.get("source_csv", "")).strip()
    if not source_csv_raw:
        raise ValueError("qa_retry.enabled is true but qa_retry.source_csv is empty.")
    source_csv = Path(source_csv_raw).expanduser()
    if not source_csv.is_absolute():
        source_csv = get_repo_root() / source_csv
    if not source_csv.exists():
        raise FileNotFoundError(f"QA retry source CSV not found: {source_csv}")

    selectors = _parse_selectors(config)
    clean_basenames = _read_clean_basenames(clean_csv)
    qa_df = _read_csv(
        source_csv,
        columns=[
            "station_name",
            "filename_base",
            "plot_timestamp",
            "quality_status",
            "failed_quality_columns",
            "failed_quality_versions",
        ],
    )
    current_df = _current_retry_rows(
        station_name=station_name,
        clean_basenames=clean_basenames,
        qa_df=qa_df,
        selectors=selectors,
    )

    with _locked_csv_transaction(state_csv):
        state_df = _read_csv(state_csv, columns=STATE_COLUMNS)

        state_map = {
            _state_key(row): {column: str(row[column]) for column in STATE_COLUMNS}
            for _, row in state_df.iterrows()
        }
        current_map = {
            _state_key(row): {column: str(row[column]) for column in MANIFEST_COLUMNS}
            for _, row in current_df.iterrows()
        }

        updated_rows: list[dict[str, str]] = []
        all_keys = sorted(set(state_map) | set(current_map))
        for key in all_keys:
            current = current_map.get(key)
            existing = state_map.get(key)

            if current is None and existing is not None:
                row = dict(existing)
                row["is_active"] = "0"
                updated_rows.append(row)
                continue

            if current is None:
                continue

            row = dict(existing or {})
            previous_status = row.get("quality_status", "")
            previous_failed_columns = row.get("failed_quality_columns", "")
            previous_failed_versions = row.get("failed_quality_versions", "")

            for column in MANIFEST_COLUMNS:
                row[column] = current[column]

            row["first_seen_at"] = row.get("first_seen_at", "") or now_timestamp
            row["last_seen_at"] = now_timestamp
            row["is_active"] = "1"

            if existing is None:
                row["admitted_at"] = ""
            elif (
                previous_status != current["quality_status"]
                or previous_failed_columns != current["failed_quality_columns"]
                or previous_failed_versions != current["failed_quality_versions"]
            ):
                row["admitted_at"] = ""
            else:
                row["admitted_at"] = row.get("admitted_at", "")

            updated_rows.append(row)

        updated_df = pd.DataFrame(updated_rows, columns=STATE_COLUMNS)
        if updated_df.empty:
            updated_df = pd.DataFrame(columns=STATE_COLUMNS)
        updated_df = updated_df.sort_values(["basename", "selector_id"], na_position="last").reset_index(drop=True)

        manifest_df = updated_df[
            (updated_df["is_active"].astype(str) == "1")
            & (updated_df["admitted_at"].astype(str).str.strip() == "")
        ][MANIFEST_COLUMNS].copy()
        manifest_df = manifest_df.sort_values(["basename", "selector_id"], na_position="last").reset_index(drop=True)

        _write_csv(state_csv, updated_df, columns=STATE_COLUMNS)
        _write_csv(output_csv, manifest_df, columns=MANIFEST_COLUMNS)
        return {
            "manifest_rows": len(manifest_df),
            "state_rows": len(updated_df),
            "active_rows": int((updated_df["is_active"].astype(str) == "1").sum()) if not updated_df.empty else 0,
        }


def mark_retry_admitted(
    *,
    state_csv: Path,
    basename: str,
    admitted_at: str,
) -> dict[str, int]:
    with _locked_csv_transaction(state_csv):
        state_df = _read_csv(state_csv, columns=STATE_COLUMNS)
        if state_df.empty:
            _write_csv(state_csv, state_df, columns=STATE_COLUMNS)
            return {"updated_rows": 0}

        basename = str(basename).strip()
        mask = (
            state_df["basename"].astype(str).str.strip().eq(basename)
            & state_df["is_active"].astype(str).str.strip().eq("1")
            & state_df["admitted_at"].astype(str).str.strip().eq("")
        )
        updated_rows = int(mask.sum())
        if updated_rows > 0:
            state_df.loc[mask, "admitted_at"] = admitted_at
            _write_csv(state_csv, state_df, columns=STATE_COLUMNS)
        return {"updated_rows": updated_rows}


def _build_manifest_cli(args: argparse.Namespace) -> int:
    summary = build_retry_manifest(
        config_paths=[Path(path).expanduser() for path in args.config_path],
        station=args.station,
        clean_csv=Path(args.clean_csv).expanduser(),
        output_csv=Path(args.output_csv).expanduser(),
        state_csv=Path(args.state_csv).expanduser(),
        now_timestamp=args.now_timestamp,
    )
    print(
        f"manifest_rows={summary['manifest_rows']} "
        f"state_rows={summary['state_rows']} "
        f"active_rows={summary['active_rows']}"
    )
    return 0


def _mark_admitted_cli(args: argparse.Namespace) -> int:
    summary = mark_retry_admitted(
        state_csv=Path(args.state_csv).expanduser(),
        basename=args.basename,
        admitted_at=args.admitted_at,
    )
    print(f"updated_rows={summary['updated_rows']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build-manifest", help="Build the station QA retry manifest.")
    build_parser.add_argument("--config-path", action="append", required=True, help="YAML config path.")
    build_parser.add_argument("--station", required=True, help="Target reprocessing station.")
    build_parser.add_argument("--clean-csv", required=True, help="STEP_0 clean metadata CSV.")
    build_parser.add_argument("--output-csv", required=True, help="QA retry manifest output CSV.")
    build_parser.add_argument("--state-csv", required=True, help="QA retry state CSV.")
    build_parser.add_argument(
        "--now-timestamp",
        default=pd.Timestamp.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        help="Timestamp written into first/last seen fields.",
    )
    build_parser.set_defaults(func=_build_manifest_cli)

    admit_parser = subparsers.add_parser("mark-admitted", help="Mark active QA retry entries as admitted.")
    admit_parser.add_argument("--state-csv", required=True, help="QA retry state CSV.")
    admit_parser.add_argument("--basename", required=True, help="Basename that entered the pipeline.")
    admit_parser.add_argument(
        "--admitted-at",
        default=pd.Timestamp.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        help="Admission timestamp.",
    )
    admit_parser.set_defaults(func=_mark_admitted_cli)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
