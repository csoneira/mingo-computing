"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/SUPPORT/SHARED_CODE/config_loader.py
Purpose: Config loader.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/SUPPORT/SHARED_CODE/config_loader.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

import csv
import re
from ast import literal_eval
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


def _parse_value(raw_value: str) -> Any:
    """Return *raw_value* converted to Python types when possible."""
    value = raw_value.strip()
    if value == "":
        return value
    lower_value = value.lower()
    if lower_value in {"true", "false"}:
        return lower_value == "true"
    try:
        parsed = literal_eval(value)
        return parsed
    except (ValueError, SyntaxError):
        bracket_stripped = value.strip()
        if bracket_stripped.startswith("[") and bracket_stripped.endswith("]"):
            inner = bracket_stripped[1:-1].strip()
            if not inner:
                return []
            tokens = [tok for tok in re.split(r"[\s,;]+", inner) if tok]
            parsed_tokens: List[Any] = []
            for token in tokens:
                try:
                    parsed_tokens.append(literal_eval(token))
                except (ValueError, SyntaxError):
                    try:
                        if "." in token or token.lower().startswith(("nan", "inf", "-")):
                            parsed_tokens.append(float(token))
                        else:
                            parsed_tokens.append(int(token))
                    except ValueError:
                        parsed_tokens.append(token)
            return parsed_tokens
        return value


def _resolve_reference_path(base_csv_path: Path, source_task: str) -> Optional[Path]:
    """Resolve a referenced task config path relative to *base_csv_path*."""
    source_task = source_task.strip()
    if not source_task:
        return None
    if source_task.endswith(".csv"):
        ref_path = Path(source_task)
        if not ref_path.is_absolute():
            ref_path = base_csv_path.parent / ref_path
        return ref_path
    task_filter_match = re.fullmatch(r"task_(\d+)_filter", source_task)
    if task_filter_match:
        task_number = task_filter_match.group(1)
        if base_csv_path.parent.name.startswith("TASK_"):
            step_1_dir = base_csv_path.parent.parent
        else:
            step_1_dir = base_csv_path.parent
        return step_1_dir / f"TASK_{task_number}" / f"config_filter_parameters_task_{task_number}.csv"
    task_match = re.fullmatch(r"task_(\d+)", source_task)
    if task_match:
        task_number = task_match.group(1)
        if base_csv_path.parent.name.startswith("TASK_"):
            step_1_dir = base_csv_path.parent.parent
        else:
            step_1_dir = base_csv_path.parent
        return step_1_dir / f"TASK_{task_number}" / f"config_parameters_task_{task_number}.csv"
    if source_task.isdigit():
        task_number = source_task
        if base_csv_path.parent.name.startswith("TASK_"):
            step_1_dir = base_csv_path.parent.parent
        else:
            step_1_dir = base_csv_path.parent
        return step_1_dir / f"TASK_{task_number}" / f"config_parameters_task_{task_number}.csv"
    filename = f"config_parameters_{source_task}.csv"
    return base_csv_path.parent / filename


def load_parameter_overrides(
    csv_path: str | Path,
    station: str,
    *,
    resolve_references: bool = True,
    _cache: Optional[Dict[Path, Dict[str, Any]]] = None,
    _stack: Optional[Set[Path]] = None,
) -> Dict[str, Any]:
    """Load parameter overrides for *station* from the CSV file."""
    parameter_csv_path = Path(csv_path)
    if not parameter_csv_path.exists():
        raise FileNotFoundError(f"Configuration parameters file not found: {csv_path}")

    if _cache is None:
        _cache = {}
    if _stack is None:
        _stack = set()
    resolved_path = parameter_csv_path.resolve()
    if resolved_path in _cache:
        return dict(_cache[resolved_path])
    if resolved_path in _stack:
        return {}
    _stack.add(resolved_path)

    overrides: Dict[str, Any] = {}
    station_column = f"station_{station}"
    reference_requests: Dict[str, str] = {}

    with parameter_csv_path.open("r", newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        if reader.fieldnames is None:
            raise ValueError(f"Configuration parameters file has no header: {csv_path}")
        headers = set(reader.fieldnames)
        use_default_only = station_column not in headers
        has_source_column = "source_task" in headers

        for row in reader:
            parameter_name = (row.get("parameter") or "").strip()
            if not parameter_name:
                continue

            source_task = (row.get("source_task") or "").strip() if has_source_column else ""
            source_task_lower = source_task.lower()
            # Allow explicit non-reference markers in source_task (e.g. plot-only params)
            # while preserving existing task-reference behavior.
            is_non_reference_marker = source_task_lower in {
                "plot_only_no_filtering",
            }
            if resolve_references and source_task and not is_non_reference_marker:
                reference_requests[parameter_name] = source_task
                continue

            value_str = ""
            if not use_default_only:
                value_str = (row.get(station_column) or "").strip()
            if value_str == "":
                value_str = (row.get("default") or "").strip()
            if value_str == "":
                # Skip empty overrides entirely.
                continue

            overrides[parameter_name] = _parse_value(value_str)

    if resolve_references and reference_requests:
        for parameter_name, source_task in reference_requests.items():
            ref_path = _resolve_reference_path(parameter_csv_path, source_task)
            if ref_path is None or not ref_path.exists():
                print(
                    f"Warning: referenced parameters file for {parameter_name} not found: {source_task}"
                )
                continue
            ref_overrides = load_parameter_overrides(
                ref_path,
                station,
                resolve_references=True,
                _cache=_cache,
                _stack=_stack,
            )
            if parameter_name in ref_overrides:
                overrides[parameter_name] = ref_overrides[parameter_name]
            else:
                print(
                    f"Warning: parameter {parameter_name} not found in referenced file {ref_path}"
                )

    _stack.remove(resolved_path)
    _cache[resolved_path] = dict(overrides)
    return overrides


def load_declared_parameter_names(csv_path: str | Path) -> Set[str]:
    """Return every declared parameter name from *csv_path*."""
    parameter_csv_path = Path(csv_path)
    if not parameter_csv_path.exists():
        raise FileNotFoundError(f"Configuration parameters file not found: {csv_path}")

    declared: Set[str] = set()
    with parameter_csv_path.open("r", newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        if reader.fieldnames is None:
            raise ValueError(f"Configuration parameters file has no header: {csv_path}")
        for row in reader:
            parameter_name = (row.get("parameter") or "").strip()
            if parameter_name:
                declared.add(parameter_name)
    return declared


def update_config_with_parameters(
    config: Dict[str, Any],
    csv_path: str | Path,
    station: str,
    *,
    resolve_references: bool = True,
) -> Dict[str, Any]:
    """Merge station-specific parameter overrides into *config*."""
    overrides = load_parameter_overrides(
        csv_path,
        station,
        resolve_references=resolve_references,
    )
    config.update(overrides)
    return config
