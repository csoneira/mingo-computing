"""Shared detector-geometry models and configuration normalization."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Iterable, List, Mapping, Tuple
import warnings

import numpy as np
import pandas as pd


GEOMETRY_SCHEMA_VERSION = 2
GEOMETRY_TOLERANCE_MM = 1.0e-9
REQUIRED_PLANE_INDICES = (1, 2, 3, 4)


@dataclass(frozen=True)
class RectBounds:
    """Axis-aligned rectangle in the shared detector coordinate system."""

    x_min: float
    x_max: float
    y_min: float
    y_max: float


# Compatibility name retained for external callers. New code should use RectBounds
# with an explicit active/readout variable name.
DetectorBounds = RectBounds


@dataclass(frozen=True)
class StripBounds:
    """Absolute readout rectangle for one one-based strip index."""

    strip_index: int
    x_min: float
    x_max: float
    y_min: float
    y_max: float


@dataclass(frozen=True)
class PlaneReadoutGeometry:
    """Normalized four-strip readout geometry for one plane."""

    plane_index: int
    strips: tuple[StripBounds, ...]
    interstrip_gap_mm: float | None
    source: str

    @property
    def x_min(self) -> float:
        return min(strip.x_min for strip in self.strips)

    @property
    def x_max(self) -> float:
        return max(strip.x_max for strip in self.strips)

    @property
    def y_min(self) -> float:
        return min(strip.y_min for strip in self.strips)

    @property
    def y_max(self) -> float:
        return max(strip.y_max for strip in self.strips)

    @property
    def interstrip_gaps_mm(self) -> tuple[float, ...]:
        return tuple(
            self.strips[index + 1].y_min - self.strips[index].y_max
            for index in range(len(self.strips) - 1)
        )


DEFAULT_ACTIVE_AREA_BOUNDS = RectBounds(
    x_min=-150.0,
    x_max=150.0,
    y_min=-143.5,
    y_max=143.5,
)
# Deprecated compatibility alias.
DEFAULT_BOUNDS = DEFAULT_ACTIVE_AREA_BOUNDS

# Legacy fallback only: old odd/even widths, centered contiguously with zero gap.
LEGACY_Y_WIDTHS = (
    (63.0, 63.0, 63.0, 98.0),
    (98.0, 63.0, 63.0, 63.0),
)
Y_WIDTHS = [np.asarray(widths, dtype=float) for widths in LEGACY_Y_WIDTHS]


def _finite_float(value: object, field_name: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a finite number, got {value!r}.") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"{field_name} must be finite, got {value!r}.")
    return parsed


def validate_rect_bounds(rect: RectBounds, name: str) -> RectBounds:
    for field_name in ("x_min", "x_max", "y_min", "y_max"):
        if not math.isfinite(float(getattr(rect, field_name))):
            raise ValueError(f"{name}.{field_name} must be finite.")
    if rect.x_min >= rect.x_max:
        raise ValueError(f"{name} requires x_min < x_max; got {rect.x_min} >= {rect.x_max}.")
    if rect.y_min >= rect.y_max:
        raise ValueError(f"{name} requires y_min < y_max; got {rect.y_min} >= {rect.y_max}.")
    return rect


def rect_bounds_to_dict(rect: RectBounds) -> dict[str, float]:
    return {
        "x_min": float(rect.x_min),
        "x_max": float(rect.x_max),
        "y_min": float(rect.y_min),
        "y_max": float(rect.y_max),
    }


def _rect_from_mapping(
    value: object,
    *,
    name: str,
    defaults: RectBounds | None = None,
) -> RectBounds:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping with x_min, x_max, y_min, and y_max.")
    fields: dict[str, float] = {}
    for field_name in ("x_min", "x_max", "y_min", "y_max"):
        if field_name in value:
            raw = value[field_name]
        elif defaults is not None:
            raw = getattr(defaults, field_name)
        else:
            raise ValueError(f"{name} is missing required field {field_name!r}.")
        fields[field_name] = _finite_float(raw, f"{name}.{field_name}")
    return validate_rect_bounds(RectBounds(**fields), name)


def resolve_active_area_bounds(
    config: Mapping[str, Any],
    *,
    warn_deprecated: bool = True,
) -> tuple[RectBounds, str]:
    """Resolve active gas bounds; the explicit key wins over the deprecated alias."""

    explicit = config.get("active_area_bounds_mm")
    legacy_present = "bounds_mm" in config
    if legacy_present and warn_deprecated:
        suffix = " and is ignored because active_area_bounds_mm is present" if explicit is not None else ""
        warnings.warn(
            "bounds_mm is deprecated for detector active geometry; use "
            f"active_area_bounds_mm{suffix}.",
            FutureWarning,
            stacklevel=2,
        )
    if explicit is not None:
        return _rect_from_mapping(explicit, name="active_area_bounds_mm"), "active_area_bounds_mm"
    if legacy_present:
        return (
            _rect_from_mapping(
                config.get("bounds_mm"),
                name="bounds_mm",
                defaults=DEFAULT_ACTIVE_AREA_BOUNDS,
            ),
            "legacy_bounds_mm",
        )
    return DEFAULT_ACTIVE_AREA_BOUNDS, "legacy_default_active_area"


def _validate_strips(plane_index: int, strips: tuple[StripBounds, ...]) -> None:
    if len(strips) != 4:
        raise ValueError(f"readout plane {plane_index} must define exactly four strips; got {len(strips)}.")
    previous: StripBounds | None = None
    for expected_index, strip in enumerate(strips, start=1):
        if strip.strip_index != expected_index:
            raise ValueError(
                f"readout plane {plane_index} strip indices must be 1..4 in increasing Y order."
            )
        for field_name in ("x_min", "x_max", "y_min", "y_max"):
            if not math.isfinite(float(getattr(strip, field_name))):
                raise ValueError(
                    f"readout plane {plane_index} strip {strip.strip_index} {field_name} must be finite."
                )
        if strip.x_min >= strip.x_max:
            raise ValueError(
                f"readout plane {plane_index} strip {strip.strip_index} requires x_min < x_max."
            )
        if strip.y_min >= strip.y_max:
            raise ValueError(
                f"readout plane {plane_index} strip {strip.strip_index} requires y_min < y_max."
            )
        if previous is not None:
            if strip.y_min < previous.y_min:
                raise ValueError(f"readout plane {plane_index} strips must be sorted by increasing Y.")
            if strip.y_min < previous.y_max - GEOMETRY_TOLERANCE_MM:
                raise ValueError(
                    f"readout plane {plane_index} strips {previous.strip_index} and "
                    f"{strip.strip_index} overlap."
                )
        previous = strip


def build_plane_readout_geometry(
    plane_index: int,
    plane_config: Mapping[str, Any],
) -> PlaneReadoutGeometry:
    """Normalize generated or explicit strip coordinates for one readout plane."""

    if not isinstance(plane_config, Mapping):
        raise ValueError(f"readout plane {plane_index} configuration must be a mapping.")
    x_min = _finite_float(plane_config.get("x_min"), f"readout plane {plane_index}.x_min")
    x_max = _finite_float(plane_config.get("x_max"), f"readout plane {plane_index}.x_max")
    if x_min >= x_max:
        raise ValueError(f"readout plane {plane_index} requires x_min < x_max.")

    explicit_present = "strip_y_bounds_mm" in plane_config
    generated_keys = {"y_min", "strip_widths_mm", "interstrip_gap_mm", "y_max"}
    generated_present = any(key in plane_config for key in generated_keys)
    if explicit_present and generated_present:
        raise ValueError(
            f"readout plane {plane_index} must use either strip_y_bounds_mm or generated "
            "y_min/strip_widths_mm/interstrip_gap_mm fields, not both."
        )
    if not explicit_present and not generated_present:
        raise ValueError(
            f"readout plane {plane_index} must define strip_y_bounds_mm or generated strip fields."
        )

    strips: list[StripBounds] = []
    configured_gap: float | None = None
    source: str
    if explicit_present:
        raw_bounds = plane_config.get("strip_y_bounds_mm")
        if not isinstance(raw_bounds, (list, tuple)) or len(raw_bounds) != 4:
            count = len(raw_bounds) if isinstance(raw_bounds, (list, tuple)) else 0
            raise ValueError(
                f"readout plane {plane_index} strip_y_bounds_mm must contain exactly four pairs; got {count}."
            )
        for strip_index, pair in enumerate(raw_bounds, start=1):
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                raise ValueError(
                    f"readout plane {plane_index} strip {strip_index} boundary must be [y_min, y_max]."
                )
            y_min = _finite_float(pair[0], f"readout plane {plane_index} strip {strip_index}.y_min")
            y_max = _finite_float(pair[1], f"readout plane {plane_index} strip {strip_index}.y_max")
            strips.append(StripBounds(strip_index, x_min, x_max, y_min, y_max))
        source = "explicit_strip_y_bounds_mm"
    else:
        required = ("y_min", "strip_widths_mm", "interstrip_gap_mm")
        missing = [key for key in required if key not in plane_config]
        if missing:
            raise ValueError(
                f"readout plane {plane_index} generated geometry is missing: {', '.join(missing)}."
            )
        y_cursor = _finite_float(plane_config["y_min"], f"readout plane {plane_index}.y_min")
        widths = plane_config["strip_widths_mm"]
        if not isinstance(widths, (list, tuple)) or len(widths) != 4:
            count = len(widths) if isinstance(widths, (list, tuple)) else 0
            raise ValueError(
                f"readout plane {plane_index} strip_widths_mm must contain exactly four values; got {count}."
            )
        configured_gap = _finite_float(
            plane_config["interstrip_gap_mm"],
            f"readout plane {plane_index}.interstrip_gap_mm",
        )
        if configured_gap < 0:
            raise ValueError(f"readout plane {plane_index} interstrip_gap_mm must be >= 0.")
        for strip_index, raw_width in enumerate(widths, start=1):
            width = _finite_float(
                raw_width,
                f"readout plane {plane_index} strip_widths_mm[{strip_index - 1}]",
            )
            if width <= 0:
                raise ValueError(
                    f"readout plane {plane_index} strip {strip_index} width must be positive."
                )
            y_max = y_cursor + width
            strips.append(StripBounds(strip_index, x_min, x_max, y_cursor, y_max))
            y_cursor = y_max + configured_gap
        derived_y_max = strips[-1].y_max
        if "y_max" in plane_config:
            configured_y_max = _finite_float(
                plane_config["y_max"],
                f"readout plane {plane_index}.y_max",
            )
            if not math.isclose(
                derived_y_max,
                configured_y_max,
                rel_tol=0.0,
                abs_tol=GEOMETRY_TOLERANCE_MM,
            ):
                raise ValueError(
                    f"readout plane {plane_index} derived y_max={derived_y_max} does not agree "
                    f"with configured y_max={configured_y_max} within {GEOMETRY_TOLERANCE_MM} mm."
                )
        source = "generated_strip_widths_and_gap"

    strips_tuple = tuple(strips)
    _validate_strips(plane_index, strips_tuple)
    return PlaneReadoutGeometry(
        plane_index=plane_index,
        strips=strips_tuple,
        interstrip_gap_mm=configured_gap,
        source=source,
    )


def build_legacy_readout_geometry(
    active_area_bounds: RectBounds,
) -> dict[int, PlaneReadoutGeometry]:
    """Reproduce the former active-X, centered-Y, contiguous-strip behavior."""

    geometry: dict[int, PlaneReadoutGeometry] = {}
    for plane_index in REQUIRED_PLANE_INDICES:
        widths = LEGACY_Y_WIDTHS[0 if plane_index in (1, 3) else 1]
        total_width = sum(widths)
        y_cursor = -total_width / 2.0
        strips: list[StripBounds] = []
        for strip_index, width in enumerate(widths, start=1):
            strips.append(
                StripBounds(
                    strip_index,
                    float(active_area_bounds.x_min),
                    float(active_area_bounds.x_max),
                    y_cursor,
                    y_cursor + width,
                )
            )
            y_cursor += width
        strips_tuple = tuple(strips)
        _validate_strips(plane_index, strips_tuple)
        geometry[plane_index] = PlaneReadoutGeometry(
            plane_index=plane_index,
            strips=strips_tuple,
            interstrip_gap_mm=0.0,
            source="legacy_active_x_centered_contiguous_y",
        )
    return geometry


def build_readout_geometry(
    config: Mapping[str, Any],
    *,
    legacy_active_area_bounds: RectBounds | None = None,
) -> tuple[dict[int, PlaneReadoutGeometry], str]:
    """Normalize all four planes, or use the explicitly marked legacy fallback."""

    readout_config = config.get("readout_geometry_mm")
    if readout_config is None:
        active = legacy_active_area_bounds or DEFAULT_ACTIVE_AREA_BOUNDS
        warnings.warn(
            "readout_geometry_mm is absent; using the deprecated legacy readout fallback "
            "(active-area X limits, centered hard-coded Y widths, zero inter-strip gap).",
            FutureWarning,
            stacklevel=2,
        )
        return build_legacy_readout_geometry(active), "legacy_fallback"
    if not isinstance(readout_config, Mapping):
        raise ValueError("readout_geometry_mm must be a mapping containing planes.")
    planes_config = readout_config.get("planes")
    if not isinstance(planes_config, Mapping):
        raise ValueError("readout_geometry_mm.planes must be a mapping defining planes 1..4.")

    normalized_keys: dict[int, object] = {}
    for raw_key, value in planes_config.items():
        try:
            plane_index = int(raw_key)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid readout plane key {raw_key!r}; expected 1, 2, 3, or 4.") from exc
        if plane_index in normalized_keys:
            raise ValueError(f"readout plane {plane_index} is defined more than once.")
        normalized_keys[plane_index] = value
    missing = sorted(set(REQUIRED_PLANE_INDICES) - set(normalized_keys))
    extra = sorted(set(normalized_keys) - set(REQUIRED_PLANE_INDICES))
    if missing:
        raise ValueError(f"readout_geometry_mm is missing required plane(s): {missing}.")
    if extra:
        raise ValueError(f"readout_geometry_mm defines unsupported plane(s): {extra}.")

    geometry = {
        plane_index: build_plane_readout_geometry(plane_index, normalized_keys[plane_index])
        for plane_index in REQUIRED_PLANE_INDICES
    }
    return geometry, "readout_geometry_mm"


def readout_geometry_to_dict(
    geometry: Mapping[int, PlaneReadoutGeometry],
    *,
    detailed: bool = True,
) -> dict[str, object]:
    planes: dict[str, object] = {}
    for plane_index in REQUIRED_PLANE_INDICES:
        plane = geometry[plane_index]
        if not detailed:
            planes[str(plane_index)] = {
                "x_min": float(plane.x_min),
                "x_max": float(plane.x_max),
                "strip_y_bounds_mm": [
                    [float(strip.y_min), float(strip.y_max)] for strip in plane.strips
                ],
            }
            continue
        planes[str(plane_index)] = {
            "source": plane.source,
            "x_min": float(plane.x_min),
            "x_max": float(plane.x_max),
            "y_min": float(plane.y_min),
            "y_max": float(plane.y_max),
            "interstrip_gap_mm": (
                None if plane.interstrip_gap_mm is None else float(plane.interstrip_gap_mm)
            ),
            "interstrip_gaps_mm": [float(value) for value in plane.interstrip_gaps_mm],
            "strip_y_bounds_mm": [
                [float(strip.y_min), float(strip.y_max)] for strip in plane.strips
            ],
            "strips": [
                {
                    "strip_index": strip.strip_index,
                    "x_min": float(strip.x_min),
                    "x_max": float(strip.x_max),
                    "y_min": float(strip.y_min),
                    "y_max": float(strip.y_max),
                }
                for strip in plane.strips
            ],
        }
    return {"planes": planes}


def get_strip_geometry(
    plane_idx: int,
    readout_geometry: Mapping[int, PlaneReadoutGeometry] | None = None,
):
    """Compatibility array view; no-config calls use only the legacy fallback."""

    geometry = readout_geometry or build_legacy_readout_geometry(DEFAULT_ACTIVE_AREA_BOUNDS)
    if plane_idx not in geometry:
        raise ValueError(f"Unknown plane index {plane_idx}; expected 1..4.")
    strips = geometry[plane_idx].strips
    widths = np.asarray([strip.y_max - strip.y_min for strip in strips], dtype=float)
    lower_edges = np.asarray([strip.y_min for strip in strips], dtype=float)
    upper_edges = np.asarray([strip.y_max for strip in strips], dtype=float)
    centres = (lower_edges + upper_edges) / 2.0
    return widths, centres, lower_edges, upper_edges


def num_strips_for_plane(
    plane_idx: int,
    readout_geometry: Mapping[int, PlaneReadoutGeometry] | None = None,
) -> int:
    return len(get_strip_geometry(plane_idx, readout_geometry)[0])


def build_geometry_map(station_df: pd.DataFrame) -> pd.DataFrame:
    geom_cols = ["P1", "P2", "P3", "P4"]
    extra_cols = [col for col in ("start", "end") if col in station_df.columns]
    unique_geoms = station_df[geom_cols + extra_cols].dropna().drop_duplicates().reset_index(drop=True)
    unique_geoms["geometry_id"] = np.arange(len(unique_geoms), dtype=int)
    merged = station_df.merge(unique_geoms, on=geom_cols, how="left")
    cols = ["station", "conf", "geometry_id", "P1", "P2", "P3", "P4"] + extra_cols
    return merged[cols]


def build_global_geometry_registry(station_dfs: List[pd.DataFrame]) -> pd.DataFrame:
    geom_cols = ["P1", "P2", "P3", "P4"]
    all_geoms = pd.concat([df[geom_cols] for df in station_dfs], ignore_index=True)
    unique_geoms = all_geoms.dropna().drop_duplicates().reset_index(drop=True)
    unique_geoms["geometry_id"] = np.arange(len(unique_geoms), dtype=int)
    return unique_geoms[["geometry_id", "P1", "P2", "P3", "P4"]]


def map_station_to_geometry(station_df: pd.DataFrame, registry: pd.DataFrame) -> pd.DataFrame:
    geom_cols = ["P1", "P2", "P3", "P4"]
    extra_cols = [col for col in ("start", "end") if col in station_df.columns]
    merged = station_df.merge(registry, on=geom_cols, how="left")
    cols = ["station", "conf", "geometry_id", "P1", "P2", "P3", "P4"] + extra_cols
    return merged[cols]


def iter_geometries(
    geom_map: pd.DataFrame,
) -> Iterable[Tuple[int, Tuple[float, float, float, float]]]:
    geom_cols = ["P1", "P2", "P3", "P4"]
    for geometry_id, group in geom_map.dropna(subset=["geometry_id"]).groupby("geometry_id"):
        values = group.iloc[0][geom_cols].to_numpy(dtype=float)
        yield int(geometry_id), (values[0], values[1], values[2], values[3])
