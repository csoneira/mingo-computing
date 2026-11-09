#!/usr/bin/env python3
"""Resolve per-step Stage 0 reprocessing station policies."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml


POLICY_FIELDS = ("stations", "reprocess_completed_stations")


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    return loaded if isinstance(loaded, dict) else {}


def _normalize_stations(value: Any) -> list[int]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [part.strip() for part in value.split(",") if part.strip()]
    if not isinstance(value, (list, tuple, set)):
        value = [value]

    stations: list[int] = []
    for item in value:
        try:
            station = int(item)
        except (TypeError, ValueError):
            continue
        if station not in stations:
            stations.append(station)
    return stations


def resolve_policy(
    shared_path: Path,
    local_path: Path,
    step: int,
) -> tuple[dict[str, list[int]], dict[str, str]]:
    """Resolve local policies, overridden by non-null shared step policies."""
    shared = _load_yaml(shared_path)
    local = _load_yaml(local_path)
    shared_step = shared.get("step_policies", {}).get(f"step_{step}", {})
    if not isinstance(shared_step, dict):
        shared_step = {}

    policy: dict[str, list[int]] = {}
    sources: dict[str, str] = {}
    for field in POLICY_FIELDS:
        shared_has_override = field in shared_step and shared_step[field] is not None
        if shared_has_override:
            policy[field] = _normalize_stations(shared_step[field])
            sources[field] = "shared"
        else:
            policy[field] = _normalize_stations(local.get(field))
            sources[field] = "local"

    # Backward compatibility for installations that have not migrated yet.
    local_has_reprocess_policy = "reprocess_completed_stations" in local
    shared_has_reprocess_override = (
        "reprocess_completed_stations" in shared_step
        and shared_step["reprocess_completed_stations"] is not None
    )
    if not local_has_reprocess_policy and not shared_has_reprocess_override:
        legacy_prefix = (
            "use_processed_as_reject_list_"
            if step == 1
            else "unpack_anyway_station_"
        )
        legacy_stations = [
            station
            for station in range(100)
            if local.get(f"{legacy_prefix}{station}") is True
        ]
        if legacy_stations:
            policy["reprocess_completed_stations"] = legacy_stations
            sources["reprocess_completed_stations"] = "legacy-local"

    return policy, sources


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shared", type=Path, required=True)
    parser.add_argument("--local", type=Path, required=True)
    parser.add_argument("--step", type=int, required=True)
    parser.add_argument("--station", type=int)
    parser.add_argument("--field", choices=POLICY_FIELDS)
    parser.add_argument("--describe", action="store_true")
    args = parser.parse_args()

    policy, sources = resolve_policy(args.shared, args.local, args.step)
    if args.describe:
        for field in POLICY_FIELDS:
            values = ",".join(str(value) for value in policy[field]) or "none"
            print(f"{field}={values} source={sources[field]}")
        return 0

    if args.station is None or args.field is None:
        parser.error("--station and --field are required unless --describe is used")
    print("true" if args.station in policy[args.field] else "false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
