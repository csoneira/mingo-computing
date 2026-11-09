from __future__ import annotations

from ast import literal_eval
from collections.abc import Mapping, Sequence
import math
import re
from typing import Any

import numpy as np
import pandas as pd


DEFAULT_OUTPUT_TRIGGER_GROUPS: tuple[dict[str, object], ...] = (
    {"name": "four_plane", "tt_values": [1234]},
    {"name": "three_plane", "tt_values": [123, 124, 134, 234]},
)


def _coerce_numeric_sequence(raw_value: Any, caster: type) -> list[float]:
    if isinstance(raw_value, (list, tuple, np.ndarray)):
        result: list[float] = []
        for item in raw_value:
            result.extend(_coerce_numeric_sequence(item, caster))
        return result
    if isinstance(raw_value, str):
        cleaned = raw_value.strip()
        if not cleaned:
            return []
        try:
            parsed = literal_eval(cleaned)
        except (ValueError, SyntaxError):
            cleaned = cleaned.replace("[", " ").replace("]", " ")
            tokens = [token for token in re.split(r"[;,\s]+", cleaned) if token]
            result = []
            for token in tokens:
                try:
                    result.append(caster(token))
                except (TypeError, ValueError):
                    continue
            return result
        return _coerce_numeric_sequence(parsed, caster)
    if np.isscalar(raw_value):
        try:
            return [caster(raw_value)]
        except (TypeError, ValueError):
            return []
    return []


def normalize_theta_boundaries(raw_value: Any, *, theta_max_deg: float = 90.0) -> list[float]:
    upper_bound = float(theta_max_deg) if math.isfinite(theta_max_deg) and theta_max_deg > 0 else 90.0
    cleaned: list[float] = []
    for value in _coerce_numeric_sequence(raw_value, float):
        if not np.isfinite(value):
            continue
        value_float = float(value)
        if 0.0 < value_float < upper_bound:
            cleaned.append(value_float)
    return sorted(dict.fromkeys(cleaned))


def normalize_region_layout(raw_value: Any, expected_regions: int) -> list[int]:
    expected = max(1, int(expected_regions))
    cleaned = [
        max(1, int(abs(value)))
        for value in _coerce_numeric_sequence(raw_value, int)
        if isinstance(value, (int, float))
    ]
    if not cleaned:
        return [1] * expected
    if len(cleaned) < expected:
        cleaned.extend([cleaned[-1]] * (expected - len(cleaned)))
    if len(cleaned) > expected:
        cleaned = cleaned[:expected]
    return cleaned


def normalize_region_ring_names(raw_value: Any, expected_regions: int) -> list[str]:
    if isinstance(raw_value, str):
        names = [token.strip() for token in re.split(r"[;,\s]+", raw_value) if token.strip()]
    elif isinstance(raw_value, Sequence) and not isinstance(raw_value, (str, bytes)):
        names = [str(value).strip() for value in raw_value if str(value).strip()]
    else:
        names = []

    expected = max(1, int(expected_regions))
    if not names:
        return [f"R{index}" for index in range(expected)]
    if len(names) < expected:
        names.extend(f"R{index}" for index in range(len(names), expected))
    if len(names) > expected:
        names = names[:expected]
    return names


def build_region_label(ring_name: str, ring_index: int, phi_index: int, n_phi: int) -> str:
    clean_name = str(ring_name).strip()
    if not clean_name:
        clean_name = f"R{ring_index}"
    if int(n_phi) <= 1:
        if clean_name.startswith("R") and clean_name[1:].isdigit():
            return f"{clean_name}.0"
        return clean_name
    if clean_name.startswith("R") and clean_name[1:].isdigit():
        return f"{clean_name}.{phi_index}"
    return f"{clean_name}_{phi_index}"


def build_angular_region_labels(
    region_layout: Sequence[int],
    *,
    region_ring_names: Sequence[str] | None = None,
) -> list[str]:
    labels: list[str] = []
    ring_names = normalize_region_ring_names(region_ring_names or [], len(region_layout))
    for ring_index, n_phi in enumerate(region_layout):
        if int(n_phi) <= 1:
            labels.append(build_region_label(ring_names[ring_index], ring_index, 0, int(n_phi)))
            continue
        labels.extend(
            build_region_label(ring_names[ring_index], ring_index, phi_index, int(n_phi))
            for phi_index in range(int(n_phi))
        )
    return labels


def classify_angular_regions(
    theta_series: pd.Series,
    phi_series: pd.Series,
    *,
    theta_boundaries: Sequence[float],
    region_layout: Sequence[int],
    region_ring_names: Sequence[str] | None = None,
    theta_max_deg: float = 90.0,
    invalid_label: str = "R_unknown",
) -> pd.Series:
    index = theta_series.index
    theta_deg = np.degrees(pd.to_numeric(theta_series, errors="coerce").to_numpy(dtype=float))
    phi_deg = np.degrees(pd.to_numeric(phi_series, errors="coerce").to_numpy(dtype=float))
    phi_wrapped = ((phi_deg + 180.0) % 360.0) - 180.0

    clean_theta_boundaries = normalize_theta_boundaries(theta_boundaries, theta_max_deg=theta_max_deg)
    clean_region_layout = normalize_region_layout(region_layout, len(clean_theta_boundaries) + 1)
    clean_region_ring_names = normalize_region_ring_names(
        region_ring_names or [],
        len(clean_region_layout),
    )
    region_bounds = [0.0, *clean_theta_boundaries, float(theta_max_deg)]

    labels = np.full(len(theta_deg), str(invalid_label), dtype=object)
    valid_theta = np.isfinite(theta_deg) & (theta_deg >= 0.0) & (theta_deg <= float(theta_max_deg))
    valid_phi = np.isfinite(phi_wrapped)

    for ring_index, (theta_min, theta_max) in enumerate(zip(region_bounds[:-1], region_bounds[1:])):
        if ring_index == len(region_bounds) - 2:
            theta_mask = valid_theta & (theta_deg >= theta_min) & (theta_deg <= theta_max)
        else:
            theta_mask = valid_theta & (theta_deg >= theta_min) & (theta_deg < theta_max)
        if not np.any(theta_mask):
            continue

        n_phi = int(clean_region_layout[ring_index])
        if n_phi <= 1:
            labels[theta_mask] = build_region_label(
                clean_region_ring_names[ring_index],
                ring_index,
                0,
                n_phi,
            )
            continue

        ring_mask = theta_mask & valid_phi
        if np.any(ring_mask):
            bin_width = 360.0 / float(n_phi)
            phi_bins = np.floor((phi_wrapped[ring_mask] + 180.0) / bin_width).astype(int) % n_phi
            labels[ring_mask] = [
                build_region_label(clean_region_ring_names[ring_index], ring_index, phi_bin, n_phi)
                for phi_bin in phi_bins
            ]
        labels[theta_mask & ~valid_phi] = str(invalid_label)

    return pd.Series(labels, index=index, dtype="object", name="region")


def normalize_output_trigger_groups(raw_groups: Any) -> list[dict[str, object]]:
    raw_sequence: Sequence[object]
    if isinstance(raw_groups, Mapping):
        raw_sequence = list(raw_groups.values())
    elif isinstance(raw_groups, Sequence) and not isinstance(raw_groups, (str, bytes)):
        raw_sequence = list(raw_groups)
    else:
        raw_sequence = list(DEFAULT_OUTPUT_TRIGGER_GROUPS)

    groups: list[dict[str, object]] = []
    for index, entry in enumerate(raw_sequence):
        if not isinstance(entry, Mapping):
            continue
        name = str(entry.get("name", f"group_{index}")).strip()
        tt_values = [
            int(value)
            for value in _coerce_numeric_sequence(entry.get("tt_values", []), int)
            if np.isfinite(value)
        ]
        tt_values = list(dict.fromkeys(tt_values))
        if not name or not tt_values:
            continue
        groups.append({"name": name, "tt_values": tt_values})

    if groups:
        return groups
    return [dict(group) for group in DEFAULT_OUTPUT_TRIGGER_GROUPS]


def build_output_column_name(
    group_name: str,
    region_label: str,
    *,
    rate_suffix: str = "rate_hz",
    include_group_name: bool = True,
) -> str:
    suffix = str(rate_suffix).strip() or "rate_hz"
    clean_region_label = str(region_label).strip()
    clean_group_name = str(group_name).strip()
    if include_group_name and clean_group_name:
        return f"{clean_group_name}_{clean_region_label}_{suffix}"
    return f"{clean_region_label}_{suffix}"


def build_output_value_columns(
    output_trigger_groups: Sequence[Mapping[str, object]],
    region_labels: Sequence[str],
    *,
    rate_suffix: str = "rate_hz",
    include_group_name: bool = True,
) -> list[str]:
    columns: list[str] = []
    for group in output_trigger_groups:
        group_name = str(group.get("name", "")).strip()
        if include_group_name and not group_name:
            continue
        columns.extend(
            build_output_column_name(
                group_name,
                region_label,
                rate_suffix=rate_suffix,
                include_group_name=include_group_name,
            )
            for region_label in region_labels
        )
    return columns


def build_tt_to_output_group(output_trigger_groups: Sequence[Mapping[str, object]]) -> dict[int, str]:
    mapping: dict[int, str] = {}
    for group in output_trigger_groups:
        group_name = str(group.get("name", "")).strip()
        if not group_name:
            continue
        for tt_value in group.get("tt_values", []):
            try:
                mapping[int(tt_value)] = group_name
            except (TypeError, ValueError):
                continue
    return mapping


def resolve_output_schema(config: Mapping[str, object]) -> dict[str, object]:
    theta_max_deg = float(config.get("angular_region_max_deg", 90.0) or 90.0)
    if not math.isfinite(theta_max_deg) or theta_max_deg <= 0.0:
        theta_max_deg = 90.0

    theta_boundaries = normalize_theta_boundaries(
        config.get("theta_boundaries", []),
        theta_max_deg=theta_max_deg,
    )
    region_layout = normalize_region_layout(
        config.get("region_layout", []),
        len(theta_boundaries) + 1,
    )
    region_ring_names = normalize_region_ring_names(
        config.get("region_ring_names", []),
        len(region_layout),
    )
    region_labels = build_angular_region_labels(
        region_layout,
        region_ring_names=region_ring_names,
    )

    output_trigger_groups = normalize_output_trigger_groups(config.get("output_trigger_groups"))
    time_column = str(config.get("output_time_column", "Time")).strip() or "Time"
    time_bin = str(config.get("output_time_bin", "1min")).strip() or "1min"
    rate_suffix = str(config.get("output_rate_suffix", "rate_hz")).strip() or "rate_hz"
    invalid_region_label = str(config.get("output_invalid_region_label", "R_unknown")).strip() or "R_unknown"
    include_group_name = bool(config.get("output_include_group_name", True))
    extra_columns = [
        str(column).strip()
        for column in (config.get("output_extra_columns") or [])
        if str(column).strip()
    ]

    explicit_columns = [
        str(column).strip()
        for column in (config.get("output_value_columns") or [])
        if str(column).strip()
    ]
    value_columns = explicit_columns or build_output_value_columns(
        output_trigger_groups,
        region_labels,
        rate_suffix=rate_suffix,
        include_group_name=include_group_name,
    )
    value_columns = list(dict.fromkeys(value_columns))

    try:
        time_bin_delta = pd.Timedelta(time_bin)
    except (TypeError, ValueError):
        time_bin = "1min"
        time_bin_delta = pd.Timedelta(time_bin)

    return {
        "theta_max_deg": theta_max_deg,
        "theta_boundaries": theta_boundaries,
        "region_layout": region_layout,
        "region_ring_names": region_ring_names,
        "region_labels": region_labels,
        "output_trigger_groups": output_trigger_groups,
        "tt_to_output_group": build_tt_to_output_group(output_trigger_groups),
        "time_column": time_column,
        "time_bin": time_bin,
        "time_bin_delta": time_bin_delta,
        "rate_suffix": rate_suffix,
        "invalid_region_label": invalid_region_label,
        "include_group_name": include_group_name,
        "value_columns": value_columns,
        "extra_columns": extra_columns,
        "column_by_group_region": {
            (str(group.get("name", "")).strip(), str(region_label).strip()): build_output_column_name(
                str(group.get("name", "")).strip(),
                str(region_label).strip(),
                rate_suffix=rate_suffix,
                include_group_name=include_group_name,
            )
            for group in output_trigger_groups
            for region_label in region_labels
        },
        "all_columns": [time_column, *value_columns, *extra_columns],
    }


def canonicalize_output_dataframe(
    dataframe: pd.DataFrame,
    *,
    time_column: str,
    value_columns: Sequence[str],
) -> pd.DataFrame:
    if dataframe.empty:
        return pd.DataFrame(columns=[time_column, *value_columns])

    source_time_column = time_column if time_column in dataframe.columns else "Time"
    out = pd.DataFrame(index=dataframe.index)
    out[time_column] = dataframe[source_time_column]

    for column in value_columns:
        if column in dataframe.columns:
            numeric = pd.to_numeric(dataframe[column], errors="coerce").fillna(0.0)
        else:
            numeric = pd.Series(0.0, index=dataframe.index, dtype=float)
        out[column] = numeric.astype(float)

    return out[[time_column, *value_columns]]
