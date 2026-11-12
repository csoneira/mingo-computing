
"""Metadata extraction and SIM_RUN identifier helpers."""

from __future__ import annotations

import hashlib
import json
from typing import Dict, Iterable, Optional, Tuple


def find_param_set_id(meta: Optional[Dict]) -> Optional[int]:
    if not meta or not isinstance(meta, dict):
        return None
    if "param_set_id" in meta:
        try:
            return int(meta["param_set_id"])
        except (TypeError, ValueError):
            return None
    upstream = meta.get("upstream")
    if isinstance(upstream, dict):
        return find_param_set_id(upstream)
    return None


def compute_step_param_id(values: Iterable[float], prefix: str) -> str:
    rounded = [round(float(val), 6) for val in values]
    payload = json.dumps({"values": rounded}, sort_keys=True, default=str, ensure_ascii=True)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{prefix}:{digest}"


def build_sim_run_name(step_ids: Iterable[str]) -> str:
    parts = []
    for val in step_ids:
        if val is None or val == "":
            continue
        try:
            num = int(float(val))
            parts.append(f"{num:03d}")
            continue
        except (ValueError, TypeError):
            parts.append(str(val))
    return "SIM_RUN_" + "_".join(parts)


def extract_param_set(meta: Optional[Dict]) -> Tuple[Optional[int], Optional[str]]:
    current = meta
    while isinstance(current, dict):
        if "param_set_id" in current:
            return current.get("param_set_id"), current.get("param_date")
        current = current.get("upstream")
    return None, None


def extract_param_row_id(meta: Optional[Dict]) -> Optional[int]:
    current = meta
    while isinstance(current, dict):
        if "param_row_id" in current:
            try:
                return int(current.get("param_row_id"))
            except (TypeError, ValueError):
                return None
        current = current.get("upstream")
    return None


def extract_step_param_ids(meta: Optional[Dict]) -> Dict[str, str]:
    ids: Dict[str, str] = {}
    current = meta
    while isinstance(current, dict):
        for key in ("step_1_param_id", "step_2_param_id", "step_3_param_id"):
            if key in current and key not in ids:
                ids[key] = str(current.get(key))
        current = current.get("upstream")
    return ids


def extract_step_id_chain(meta: Optional[Dict]) -> list[str]:
    chain: dict[str, str] = {}
    current = meta
    while isinstance(current, dict):
        for idx in range(1, 11):
            key = f"step_{idx}_id"
            if key in current and key not in chain:
                chain[key] = str(current.get(key))
        current = current.get("upstream")
    ordered = []
    for idx in range(1, 11):
        key = f"step_{idx}_id"
        if key in chain:
            ordered.append(chain[key])
    return ordered
