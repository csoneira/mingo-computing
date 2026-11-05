#!/usr/bin/env python3
"""Assign automatic one-hot gates to consecutive Stage 1 product events."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import hashlib
from pathlib import Path
import pickle
import re
from typing import Any, Mapping, Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import yaml
from scipy.interpolate import CubicSpline
from scipy.ndimage import gaussian_filter1d
from scipy.stats import norm

from calibration_context import (
    generate_calibration_context,
    generate_calibration_temperature_plots,
)
from environment_context import REDUCED_FIELD_COLUMN, generate_environment_context
from event_gate_streaming import (
    StreamingAngularHistograms,
    StreamingChargeClusterHistograms,
    StreamingGateAggregates,
    StreamingPlaneEfficiencyMaps,
    StreamingPlaneXYHistograms,
    efficiency_summary_frame,
    enabled_gate_comparison_frame,
    gate_rate_frame,
    gate_summary_frame,
)
from mingo00_product_selection import (
    Mingo00Selection,
    select_mingo00_products,
    validate_close_parameters,
)


ANALYSIS_ROOT = Path(__file__).resolve().parents[3]
STATIONS_ROOT = ANALYSIS_ROOT / "MINGO_ANALYSIS_STATIONS"
DEFAULT_CONFIG = Path(__file__).with_name("config_test_3_event_gates.yaml")
TOT_TO_CHARGE_CALIBRATION = (
    ANALYSIS_ROOT
    / "MINGO_ANALYSIS_SCRIPTS"
    / "ANCILLARY"
    / "CALIBRATIONS_AND_LUTS"
    / "TOT_TO_CHARGE_CAL"
    / "tot_to_charge_calibration.csv"
)
OUTPUT_NAME = "TEST_3_CONFIGURABLE_GATES"
BASENAME_RE = re.compile(r"mi0[0-9]\d{11}")
COMBINATORS = frozenset({"all", "any", "not"})
NUMERIC_OPERATORS = frozenset({"lt", "le", "gt", "ge", "between"})
EFFICIENCY_PRODUCT_MODES = {
    "all_planes": (1, 2, 3, 4),
    "planes_2_and_3": (2, 3, 2, 3),
}


@dataclass(frozen=True)
class Product:
    path: Path
    basename: str
    acquired: datetime


@dataclass(frozen=True)
class Gate:
    code: str
    bit_value: int
    name: str
    condition: Mapping[str, Any]
    short_label: str = ""

    @property
    def binary_code(self) -> str:
        return format(self.bit_value, "b")


def efficiency_product_setting(config: dict[str, Any]) -> dict[str, Any]:
    mode = str(config.get("efficiency_product_planes", "all_planes")).strip().lower()
    if mode not in EFFICIENCY_PRODUCT_MODES:
        allowed = ", ".join(EFFICIENCY_PRODUCT_MODES)
        raise ValueError(
            f"efficiency_product_planes must be one of: {allowed}; got {mode!r}"
        )
    planes = EFFICIENCY_PRODUCT_MODES[mode]
    return {
        "efficiency_product_mode": mode,
        "efficiency_product_planes": planes,
        "efficiency_product_label": (
            "all four plane efficiencies"
            if mode == "all_planes"
            else "squared inner-plane product (plane 2 × plane 3)²"
        ),
    }


def efficiency_product_from_frame(
    frame: pd.DataFrame, planes: tuple[int, ...], *, column_template: str,
) -> pd.Series:
    columns = [column_template.format(plane=plane) for plane in planes]
    return frame[columns].prod(axis=1, min_count=len(columns))


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    return parser.parse_args()


def station_name(value: Any) -> str:
    text = str(value).strip().upper().removeprefix("MINGO")
    try:
        number = int(text)
    except ValueError as exc:
        raise ValueError(f"Invalid station {value!r}; use 1, 01, or MINGO01") from exc
    if not 0 <= number <= 99:
        raise ValueError(f"Station number outside supported range: {number}")
    return f"MINGO{number:02d}"


def boundary(value: Any, *, is_end: bool) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, date):
        parsed = datetime.combine(value, time.min)
        return parsed + timedelta(days=1) - timedelta(microseconds=1) if is_end else parsed
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid ISO date/datetime: {value!r}") from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    if is_end and re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        parsed += timedelta(days=1) - timedelta(microseconds=1)
    return parsed


def acquisition_time(basename: str) -> datetime | None:
    if not BASENAME_RE.fullmatch(basename):
        return None
    stamp = basename[4:]
    try:
        year = 2000 + int(stamp[:2])
        doy = int(stamp[2:5])
        if not 1 <= doy <= 366:
            return None
        parsed = datetime(year, 1, 1) + timedelta(
            days=doy - 1,
            hours=int(stamp[5:7]),
            minutes=int(stamp[7:9]),
            seconds=int(stamp[9:11]),
        )
    except (ValueError, OverflowError):
        return None
    return parsed if parsed.year == year else None


def parquet_basename(path: Path) -> str | None:
    name = path.stem
    for prefix in ("postprocessed_", "fitted_", "listed_", "calibrated_", "cleaned_", "raw_"):
        if name.startswith(prefix):
            name = name.removeprefix(prefix)
            break
    return name if BASENAME_RE.fullmatch(name) else None


def load_configuration(path: Path) -> dict[str, Any]:
    runtime_path = path.expanduser().resolve()
    with runtime_path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    if not isinstance(config, dict):
        raise ValueError("Config root must be a YAML mapping")
    has_inline_gates = "gates" in config
    has_gate_config = "gates_config" in config
    if has_inline_gates == has_gate_config:
        raise ValueError(
            "Runtime config must define exactly one of gates_config or inline gates"
        )
    config_paths = [runtime_path]
    if has_gate_config:
        configured_path = Path(str(config["gates_config"]).strip()).expanduser()
        gate_path = (
            configured_path
            if configured_path.is_absolute()
            else runtime_path.parent / configured_path
        ).resolve()
        with gate_path.open("r", encoding="utf-8") as handle:
            gate_config = yaml.safe_load(handle) or {}
        if not isinstance(gate_config, dict):
            raise ValueError("Gate config root must be a YAML mapping")
        if "gates" not in gate_config:
            raise ValueError(f"Gate config has no gates list: {gate_path}")
        config["gates"] = gate_config["gates"]
        config["gates_config_path"] = gate_path
        config_paths.append(gate_path)
    required = ("station", "max_datafiles")
    missing = [key for key in required if key not in config]
    if missing:
        raise ValueError("Missing config fields: " + ", ".join(missing))
    resolved_station = station_name(config["station"])
    if resolved_station == "MINGO00":
        close_parameters = validate_close_parameters(config.get("mingo00_close_parameters"))
        # MINGO00 acquisition dates are synthetic and must not restrict candidates.
        start = datetime(2000, 1, 1)
        end = datetime(2100, 1, 1) - timedelta(microseconds=1)
    else:
        date_missing = [key for key in ("start_date", "end_date") if key not in config]
        if date_missing:
            raise ValueError("Missing config fields: " + ", ".join(date_missing))
        start = boundary(config["start_date"], is_end=False)
        end = boundary(config["end_date"], is_end=True)
        close_parameters = (
            validate_close_parameters(config["mingo00_close_parameters"])
            if "mingo00_close_parameters" in config
            else ()
        )
    maximum = int(config["max_datafiles"])
    if start > end or maximum < 1:
        raise ValueError("Require start_date <= end_date and max_datafiles >= 1")
    config.update(
        station_name=resolved_station,
        start=start,
        end=end,
        maximum=maximum,
        close_parameters=close_parameters,
        config_paths=tuple(config_paths),
    )
    return config


def discover(lake: Path, start: datetime, end: datetime) -> list[Product]:
    if not lake.is_dir():
        raise FileNotFoundError(f"Parquet lake not found: {lake}")
    products: list[Product] = []
    for path in lake.glob("*.parquet"):
        basename = parquet_basename(path)
        acquired = acquisition_time(basename) if basename else None
        if basename and acquired and start <= acquired <= end:
            products.append(Product(path, basename, acquired))
    products.sort(key=lambda item: (item.acquired, item.basename))
    if not products:
        raise ValueError(f"No product files between {start.isoformat()} and {end.isoformat()}")
    return products


def tightest_block(files: list[Product], maximum: int) -> list[Product]:
    """Select the same minimum-span contiguous chronological block as Test 2."""
    count = min(maximum, len(files))
    if count == len(files):
        return files
    index = min(
        range(len(files) - count + 1),
        key=lambda i: (files[i + count - 1].acquired - files[i].acquired, files[i].acquired),
    )
    return files[index:index + count]


def schemas(files: list[Product]) -> tuple[list[str], dict[str, set[str]]]:
    columns: list[str] = []
    types: dict[str, set[str]] = {}
    for product in files:
        for field in pq.read_schema(product.path):
            if field.name not in types:
                columns.append(field.name)
            types.setdefault(field.name, set()).add(str(field.type))
    return columns, types


def show_columns(columns: list[str], types: dict[str, set[str]]) -> None:
    print(f"\nAvailable parquet columns in selected files ({len(columns)}):")
    for index, name in enumerate(columns, 1):
        print(f"  {index:03d}. {name:<52} [{' | '.join(sorted(types[name]))}]")
    print()


def parse_gates(raw_gates: Any) -> list[Gate]:
    if not isinstance(raw_gates, list) or not raw_gates:
        raise ValueError("gates must be a nonempty YAML list")
    gates: list[Gate] = []
    used_names: set[str] = set()
    used_labels: set[str] = set()
    for index, raw_gate in enumerate(raw_gates, 1):
        if not isinstance(raw_gate, dict):
            raise ValueError(f"gates item {index} must be a mapping")
        if "code" in raw_gate:
            raise ValueError(
                f"gates item {index} must not define code; codes are assigned "
                "automatically from enabled order"
            )
        enabled = raw_gate.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ValueError(f"gates item {index} enabled must be true or false")
        name = str(raw_gate.get("name", f"gate_{index}")).strip()
        short_label = str(raw_gate.get("short_label", "")).strip()
        if not name:
            raise ValueError(f"gates item {index} needs a nonempty name")
        if not short_label or len(short_label) > 16:
            raise ValueError(
                f"Gate {name!r} short_label must contain 1..16 characters"
            )
        if name in used_names or short_label in used_labels:
            raise ValueError(
                f"Duplicate gate name or short_label at gates item {index}"
            )
        condition = raw_gate.get("condition")
        if not isinstance(condition, dict):
            raise ValueError(f"Gate {short_label!r} needs a condition mapping")
        used_names.add(name)
        used_labels.add(short_label)
        if enabled:
            if len(gates) >= 62:
                raise ValueError("At most 62 gates can be enabled")
            bit_value = 1 << len(gates)
            gates.append(
                Gate(str(bit_value), bit_value, name, condition, short_label)
            )
        else:
            print(f"Disabled gate {short_label} ({name})")
    if not gates:
        raise ValueError("At least one gate must have enabled: true")
    print("Enabled gate assignments (short_label: binary -> decimal):")
    for gate in gates:
        print(
            f"  {gate.short_label}: {gate.binary_code} -> {gate.code}"
        )
    return gates


def gate_from_short_label(
    gates: list[Gate], short_label: Any, *, location: str,
) -> Gate:
    identifier = str(short_label).strip()
    matches = [gate for gate in gates if gate.short_label == identifier]
    if len(matches) != 1:
        available = ", ".join(gate.short_label for gate in gates)
        raise ValueError(
            f"{location} references unknown enabled gate short_label "
            f"{identifier!r}; available: {available}"
        )
    return matches[0]


def combined_decimal_code_from_labels(
    gates: list[Gate], labels: Any, *, location: str,
) -> str:
    if not isinstance(labels, list) or not labels:
        raise ValueError(f"{location} must be a nonempty list of gate short labels")
    selected = [
        gate_from_short_label(gates, label, location=location) for label in labels
    ]
    if len({gate.short_label for gate in selected}) != len(selected):
        raise ValueError(f"{location} contains duplicate gate short labels")
    return str(sum(gate.bit_value for gate in selected))


def condition_columns(node: Any, *, location: str = "condition") -> set[str]:
    if not isinstance(node, dict):
        raise ValueError(f"{location} must be a mapping")
    combinators = [key for key in COMBINATORS if key in node]
    if combinators:
        if len(combinators) != 1 or len(node) != 1:
            raise ValueError(f"{location} must contain exactly one all/any/not operator")
        operator = combinators[0]
        children = node[operator]
        if operator == "not":
            return condition_columns(children, location=f"{location}.not")
        if not isinstance(children, list) or not children:
            raise ValueError(f"{location}.{operator} must be a nonempty list")
        result: set[str] = set()
        for index, child in enumerate(children):
            result.update(condition_columns(child, location=f"{location}.{operator}[{index}]"))
        return result
    column = str(node.get("column", "")).strip()
    operator = str(node.get("op", node.get("operator", ""))).strip().lower()
    if not column or not operator:
        raise ValueError(f"{location} leaf needs column and op")
    columns = {column}
    if operator in {"abs_diff_lt", "abs_diff_le"}:
        other_column = str(node.get("other_column", "")).strip()
        if not other_column:
            raise ValueError(f"{location} {operator} needs other_column")
        columns.add(other_column)
    if operator == "projected_inside_circle":
        for key in ("y_column", "x_slope_column", "y_slope_column", "z_column"):
            referenced_column = str(node.get(key, "")).strip()
            if not referenced_column:
                raise ValueError(f"{location} {operator} needs {key}")
            columns.add(referenced_column)
    return columns


def derived_topology_setting(config: dict[str, Any]) -> dict[str, Any]:
    raw = config.get("derived_strip_topology", {})
    if raw is False:
        return {"enabled": False, "source_suffix": "qsum_cal", "threshold": 0.0, "active_when": "gt"}
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("derived_strip_topology must be a YAML mapping or false")
    active_when = str(raw.get("active_when", "gt")).strip().lower()
    if active_when not in {"gt", "ge"}:
        raise ValueError("derived_strip_topology.active_when must be gt or ge")
    return {
        "enabled": bool(raw.get("enabled", True)),
        "source_suffix": str(raw.get("source_suffix", "qsum_cal")).strip(),
        "threshold": float(raw.get("threshold", 0.0)),
        "active_when": active_when,
    }


def derived_column_names() -> list[str]:
    return [
        name
        for plane in range(1, 5)
        for name in (f"p{plane}_cluster_size", f"p{plane}_strip_topology")
    ]


def topology_source_columns(setting: dict[str, Any]) -> list[str]:
    if not setting["enabled"]:
        return []
    suffix = setting["source_suffix"]
    return [f"p{plane}_s{strip}_{suffix}" for plane in range(1, 5) for strip in range(1, 5)]


def charge_cluster_size_study_setting(
    config: dict[str, Any],
    available: set[str],
    topology_setting: dict[str, Any],
) -> dict[str, Any] | None:
    raw = config.get("charge_cluster_size_study", False)
    if raw is False:
        return None
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("charge_cluster_size_study must be a YAML mapping or false")
    if not bool(raw.get("enabled", True)):
        return None
    if not topology_setting["enabled"]:
        raise ValueError(
            "charge_cluster_size_study requires derived_strip_topology.enabled"
        )
    charge_columns = [f"p{plane}_qsum" for plane in range(1, 5)]
    missing = sorted(set(charge_columns) - available)
    if missing:
        raise ValueError(
            "Charge cluster-size study columns absent from schema: "
            + ", ".join(missing)
        )
    bins = int(raw.get("bins", 160))
    if bins < 5:
        raise ValueError("charge_cluster_size_study.bins must be at least 5")
    raw_range = raw.get("x_range", [0, 500])
    if not isinstance(raw_range, (list, tuple)) or len(raw_range) != 2:
        raise ValueError("charge_cluster_size_study.x_range needs [lower, upper]")
    lower, upper = float(raw_range[0]), float(raw_range[1])
    if not np.isfinite(lower) or not np.isfinite(upper) or lower >= upper:
        raise ValueError(
            "charge_cluster_size_study.x_range must contain finite increasing values"
        )
    return {
        "charge_columns": charge_columns,
        "bins": bins,
        "x_range": (lower, upper),
    }


def plane_xy_histogram_setting(
    config: dict[str, Any],
    available: set[str],
) -> dict[str, Any] | None:
    raw = config.get("plane_xy_histograms", False)
    if raw is False:
        return None
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("plane_xy_histograms must be a YAML mapping or false")
    if not bool(raw.get("enabled", True)):
        return None
    columns = {
        "x_column": str(raw.get("x_column", "event_x")).strip(),
        "y_column": str(raw.get("y_column", "event_y")).strip(),
        "x_slope_column": str(raw.get("x_slope_column", "event_xp")).strip(),
        "y_slope_column": str(raw.get("y_slope_column", "event_yp")).strip(),
        "z_columns": [f"z_p{plane}" for plane in range(1, 5)],
    }
    required = {
        columns["x_column"], columns["y_column"],
        columns["x_slope_column"], columns["y_slope_column"],
        *columns["z_columns"],
    }
    missing = sorted(required - available)
    if missing:
        raise ValueError(
            "Plane X/Y histogram columns absent from schema: " + ", ".join(missing)
        )
    bins = int(raw.get("bins", 100))
    if bins < 5:
        raise ValueError("plane_xy_histograms.bins must be at least 5")
    ranges: dict[str, tuple[float, float]] = {}
    for axis in ("x", "y"):
        raw_range = raw.get(f"{axis}_range", [-220, 220])
        if not isinstance(raw_range, (list, tuple)) or len(raw_range) != 2:
            raise ValueError(
                f"plane_xy_histograms.{axis}_range needs [lower, upper]"
            )
        lower, upper = float(raw_range[0]), float(raw_range[1])
        if not np.isfinite(lower) or not np.isfinite(upper) or lower >= upper:
            raise ValueError(
                f"plane_xy_histograms.{axis}_range must be finite and increasing"
            )
        ranges[f"{axis}_range"] = (lower, upper)
    return {**columns, "columns": sorted(required), "bins": bins, **ranges}


def plane_efficiency_map_setting(
    config: dict[str, Any],
    available: set[str],
) -> dict[str, Any] | None:
    raw = config.get("efficiency_plane", False)
    if raw is False:
        return None
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("efficiency_plane must be a YAML mapping or false")
    if not bool(raw.get("enabled", True)):
        return None
    xy_defaults = config.get("plane_xy_histograms", {})
    if not isinstance(xy_defaults, dict):
        xy_defaults = {}
    columns = {
        "x_column": str(
            raw.get("x_column", xy_defaults.get("x_column", "event_x"))
        ).strip(),
        "y_column": str(
            raw.get("y_column", xy_defaults.get("y_column", "event_y"))
        ).strip(),
        "x_slope_column": str(
            raw.get(
                "x_slope_column",
                xy_defaults.get("x_slope_column", "event_xp"),
            )
        ).strip(),
        "y_slope_column": str(
            raw.get(
                "y_slope_column",
                xy_defaults.get("y_slope_column", "event_yp"),
            )
        ).strip(),
        "topology_column": str(
            raw.get("topology_column", "tt_task3_list")
        ).strip(),
        "z_columns": [f"z_p{plane}" for plane in range(1, 5)],
    }
    required = {
        columns["x_column"], columns["y_column"],
        columns["x_slope_column"], columns["y_slope_column"],
        columns["topology_column"], *columns["z_columns"],
    }
    missing = sorted(required - available)
    if missing:
        raise ValueError(
            "Plane-efficiency map columns absent from schema: "
            + ", ".join(missing)
        )
    bins = int(raw.get("bins", xy_defaults.get("bins", 100)))
    if bins < 5:
        raise ValueError("efficiency_plane.bins must be at least 5")
    ranges: dict[str, tuple[float, float]] = {}
    for axis in ("x", "y"):
        raw_range = raw.get(
            f"{axis}_range",
            xy_defaults.get(f"{axis}_range", [-220, 220]),
        )
        if not isinstance(raw_range, (list, tuple)) or len(raw_range) != 2:
            raise ValueError(
                f"efficiency_plane.{axis}_range needs [lower, upper]"
            )
        lower, upper = float(raw_range[0]), float(raw_range[1])
        if not np.isfinite(lower) or not np.isfinite(upper) or lower >= upper:
            raise ValueError(
                f"efficiency_plane.{axis}_range must be finite and increasing"
            )
        ranges[f"{axis}_range"] = (lower, upper)
    return {**columns, "columns": sorted(required), "bins": bins, **ranges}


def read_events(files: list[Product], columns: list[str]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for product in files:
        present = set(pq.read_schema(product.path).names)
        frame = pd.read_parquet(product.path, columns=[name for name in columns if name in present])
        for name in columns:
            if name not in frame:
                frame[name] = np.nan
        frame = frame[columns]
        frame["_source_basename"] = product.basename
        frames.append(frame)
        print(f"Loaded {len(frame):,} events from {product.basename}")
    return pd.concat(frames, ignore_index=True)


def stream_events(
    files: list[Product],
    columns: list[str],
    gates: list[Gate],
    topology_setting: dict[str, Any],
    *,
    time_column: str,
    topology_column: str,
    window: pd.Timedelta,
    angular_histogram_setting: dict[str, Any] | None = None,
    charge_cluster_setting: dict[str, Any] | None = None,
    plane_xy_setting: dict[str, Any] | None = None,
    plane_efficiency_setting: dict[str, Any] | None = None,
    batch_size: int = 100_000,
    checkpoint_path: Path | None = None,
    fingerprint: str = "",
    checkpoint_every_files: int = 10,
) -> StreamingGateAggregates:
    """Evaluate and reduce disposable Arrow batches without joining event rows."""
    aggregates = StreamingGateAggregates(
        window,
        angular_histograms=(
            StreamingAngularHistograms(angular_histogram_setting)
            if angular_histogram_setting is not None else None
        ),
        charge_cluster_histograms=(
            StreamingChargeClusterHistograms(
                np.linspace(
                    charge_cluster_setting["x_range"][0],
                    charge_cluster_setting["x_range"][1],
                    charge_cluster_setting["bins"] + 1,
                )
            )
            if charge_cluster_setting is not None else None
        ),
        plane_xy_histograms=(
            StreamingPlaneXYHistograms(
                plane_xy_setting,
                np.linspace(
                    plane_xy_setting["x_range"][0],
                    plane_xy_setting["x_range"][1],
                    plane_xy_setting["bins"] + 1,
                ),
                np.linspace(
                    plane_xy_setting["y_range"][0],
                    plane_xy_setting["y_range"][1],
                    plane_xy_setting["bins"] + 1,
                ),
            )
            if plane_xy_setting is not None else None
        ),
        plane_efficiency_maps=(
            StreamingPlaneEfficiencyMaps(
                plane_efficiency_setting,
                np.linspace(
                    plane_efficiency_setting["x_range"][0],
                    plane_efficiency_setting["x_range"][1],
                    plane_efficiency_setting["bins"] + 1,
                ),
                np.linspace(
                    plane_efficiency_setting["y_range"][0],
                    plane_efficiency_setting["y_range"][1],
                    plane_efficiency_setting["bins"] + 1,
                ),
            )
            if plane_efficiency_setting is not None else None
        ),
    )
    completed: list[str] = []
    if checkpoint_path is not None and checkpoint_path.is_file():
        try:
            with checkpoint_path.open("rb") as handle:
                payload = pickle.load(handle)
            cached_completed = list(payload["completed"])
            expected_prefix = [
                product.basename for product in files[:len(cached_completed)]
            ]
            if (
                payload.get("fingerprint") == fingerprint
                and cached_completed == expected_prefix
                and payload["aggregates"].window == window
            ):
                aggregates = payload["aggregates"]
                completed = cached_completed
                print(
                    f"Resuming streaming checkpoint after {len(completed)}/"
                    f"{len(files)} files: {checkpoint_path}"
                )
        except (
            OSError, EOFError, AttributeError, KeyError, TypeError, ValueError,
            pickle.PickleError,
        ) as exc:
            print(f"Ignoring unreadable streaming checkpoint {checkpoint_path}: {exc}")

    for file_index, product in enumerate(files[len(completed):], len(completed) + 1):
        parquet = pq.ParquetFile(product.path)
        present = set(parquet.schema_arrow.names)
        read_columns = [name for name in columns if name in present]
        file_rows = 0
        for record_batch in parquet.iter_batches(
            batch_size=batch_size, columns=read_columns,
        ):
            frame = record_batch.to_pandas()
            for name in columns:
                if name not in frame:
                    frame[name] = np.nan
            frame = frame[columns]
            add_derived_topology_columns(frame, topology_setting, verbose=False)
            masks = assign_gates(frame, gates, verbose=False)
            topologies = (
                frame[topology_column]
                if topology_column in frame
                else pd.Series(pd.NA, index=frame.index, dtype="string")
            )
            if topology_column:
                topology_numeric = pd.to_numeric(topologies, errors="coerce")
                topologies = (
                    topology_numeric.where(topology_numeric.mod(1).eq(0))
                    .astype("Int64")
                    .astype("string")
                )
            timestamps = (
                frame[time_column]
                if time_column else pd.Series(pd.NaT, index=frame.index)
            )
            aggregates.accumulate(
                timestamps, topologies, frame["gate_code"], masks,
            )
            if aggregates.angular_histograms is not None:
                aggregates.angular_histograms.accumulate(
                    frame, frame["gate_code"], masks,
                )
            if aggregates.charge_cluster_histograms is not None:
                aggregates.charge_cluster_histograms.accumulate(frame, masks)
            if aggregates.plane_xy_histograms is not None:
                aggregates.plane_xy_histograms.accumulate(frame, masks)
            if aggregates.plane_efficiency_maps is not None:
                aggregates.plane_efficiency_maps.accumulate(
                    frame, topologies, masks,
                )
            file_rows += len(frame)
        print(
            f"Streamed {file_rows:,} events from {product.basename} "
            f"({file_index}/{len(files)}); retained aggregate windows only"
        )
        completed.append(product.basename)
        if (
            checkpoint_path is not None
            and (
                len(completed) == len(files)
                or len(completed) % checkpoint_every_files == 0
            )
        ):
            checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = checkpoint_path.with_suffix(checkpoint_path.suffix + ".tmp")
            with temporary.open("wb") as handle:
                pickle.dump(
                    {
                        "fingerprint": fingerprint,
                        "completed": completed,
                        "aggregates": aggregates,
                    },
                    handle,
                    protocol=pickle.HIGHEST_PROTOCOL,
                )
            temporary.replace(checkpoint_path)
            print(
                f"Saved streaming checkpoint after {len(completed)}/"
                f"{len(files)} files: {checkpoint_path}"
            )
    return aggregates


def streaming_fingerprint(
    config_paths: Path | Sequence[Path],
    files: list[Product],
    columns: list[str],
    layout: tuple[str, str, pd.Timedelta],
) -> str:
    """Hash every input that can change exact streaming reductions."""
    digest = hashlib.sha256()
    paths = (
        [config_paths]
        if isinstance(config_paths, Path)
        else list(config_paths)
    )
    for config_path in paths:
        resolved = config_path.expanduser().resolve()
        digest.update(str(resolved).encode("utf-8"))
        digest.update(resolved.read_bytes())
    digest.update(Path(__file__).read_bytes())
    digest.update((Path(__file__).with_name("event_gate_streaming.py")).read_bytes())
    digest.update(repr((columns, layout)).encode("utf-8"))
    for product in files:
        status = product.path.stat()
        digest.update(
            f"{product.path.resolve()}\0{status.st_size}\0{status.st_mtime_ns}\n".encode()
        )
    return digest.hexdigest()


def add_derived_topology_columns(
    frame: pd.DataFrame,
    setting: dict[str, Any],
    *,
    verbose: bool = True,
) -> None:
    if not setting["enabled"]:
        return
    suffix = setting["source_suffix"]
    threshold = setting["threshold"]
    for plane in range(1, 5):
        columns = [f"p{plane}_s{strip}_{suffix}" for strip in range(1, 5)]
        numeric = frame[columns].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
        finite = np.isfinite(numeric)
        if setting["active_when"] == "ge":
            active = finite & (numeric >= threshold)
        else:
            active = finite & (numeric > threshold)
        frame[f"p{plane}_cluster_size"] = active.sum(axis=1).astype(np.int8)
        frame[f"p{plane}_strip_topology"] = [
            "".join("1" if state else "0" for state in row) for row in active
        ]
    if verbose:
        print(
            "Derived p#_cluster_size and p#_strip_topology from "
            f"p#_s#_{suffix} ({setting['active_when']} {threshold:g})."
        )


def _is_numeric_scalar(value: Any) -> bool:
    return isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(value, bool)


def evaluate_leaf(frame: pd.DataFrame, node: Mapping[str, Any], location: str) -> pd.Series:
    column = str(node.get("column", "")).strip()
    operator = str(node.get("op", node.get("operator", ""))).strip().lower()
    if column not in frame.columns:
        raise ValueError(f"{location} references unavailable column {column!r}")
    series = frame[column]
    if operator in {"abs_diff_lt", "abs_diff_le"}:
        other_column = str(node.get("other_column", "")).strip()
        if not other_column:
            raise ValueError(f"{location} {operator} needs other_column")
        if other_column not in frame.columns:
            raise ValueError(
                f"{location} references unavailable column {other_column!r}"
            )
        if "value" not in node:
            raise ValueError(f"{location} {operator} needs value")
        limit = float(node["value"])
        if not np.isfinite(limit) or limit < 0:
            raise ValueError(f"{location} {operator} value must be finite and nonnegative")
        left = pd.to_numeric(series, errors="coerce")
        right = pd.to_numeric(frame[other_column], errors="coerce")
        valid = left.notna() & right.notna() & np.isfinite(left) & np.isfinite(right)
        difference = (left - right).abs()
        comparison = difference.lt(limit) if operator == "abs_diff_lt" else difference.le(limit)
        return valid & comparison
    if operator == "projected_inside_circle":
        referenced = {
            key: str(node.get(key, "")).strip()
            for key in ("y_column", "x_slope_column", "y_slope_column", "z_column")
        }
        for key, referenced_column in referenced.items():
            if not referenced_column:
                raise ValueError(f"{location} {operator} needs {key}")
            if referenced_column not in frame.columns:
                raise ValueError(
                    f"{location} references unavailable column {referenced_column!r}"
                )
        if "radius" not in node:
            raise ValueError(f"{location} {operator} needs radius")
        radius = float(node["radius"])
        if not np.isfinite(radius) or radius <= 0:
            raise ValueError(f"{location} {operator} radius must be finite and positive")
        center = node.get("center", [0.0, 0.0])
        if not isinstance(center, (list, tuple)) or len(center) != 2:
            raise ValueError(f"{location} {operator} center must be [x, y]")
        center_x, center_y = float(center[0]), float(center[1])
        if not np.isfinite(center_x) or not np.isfinite(center_y):
            raise ValueError(f"{location} {operator} center must be finite")

        numeric_columns = {
            "x": pd.to_numeric(series, errors="coerce"),
            **{
                key: pd.to_numeric(frame[referenced_column], errors="coerce")
                for key, referenced_column in referenced.items()
            },
        }
        valid = pd.Series(True, index=frame.index, dtype=bool)
        for numeric in numeric_columns.values():
            valid &= numeric.notna() & np.isfinite(numeric)
        projected_x = (
            numeric_columns["x"]
            + numeric_columns["x_slope_column"] * numeric_columns["z_column"]
            - center_x
        )
        projected_y = (
            numeric_columns["y_column"]
            + numeric_columns["y_slope_column"] * numeric_columns["z_column"]
            - center_y
        )
        return valid & (projected_x.pow(2) + projected_y.pow(2)).le(radius**2)
    if operator in NUMERIC_OPERATORS:
        numeric = pd.to_numeric(series, errors="coerce")
        valid = numeric.notna() & np.isfinite(numeric)
        if operator == "between":
            bounds = node.get("values", node.get("value"))
            if not isinstance(bounds, (list, tuple)) or len(bounds) != 2:
                raise ValueError(f"{location} between needs values: [lower, upper]")
            lower, upper = float(bounds[0]), float(bounds[1])
            if lower > upper:
                raise ValueError(f"{location} between lower bound exceeds upper bound")
            return valid & numeric.between(lower, upper, inclusive="both")
        if "value" not in node:
            raise ValueError(f"{location} {operator} needs value")
        value = float(node["value"])
        comparison = {
            "lt": numeric < value,
            "le": numeric <= value,
            "gt": numeric > value,
            "ge": numeric >= value,
        }[operator]
        return valid & comparison
    if operator in {"eq", "ne"}:
        if "value" not in node:
            raise ValueError(f"{location} {operator} needs value")
        value = node["value"]
        if _is_numeric_scalar(value):
            comparable = pd.to_numeric(series, errors="coerce")
            valid = comparable.notna() & np.isfinite(comparable)
            result = comparable.eq(float(value)) if operator == "eq" else comparable.ne(float(value))
        else:
            comparable = series.astype("string")
            valid = comparable.notna()
            result = comparable.eq(str(value)) if operator == "eq" else comparable.ne(str(value))
        return valid & result
    if operator in {"in", "not_in"}:
        values = node.get("values", node.get("value"))
        if not isinstance(values, (list, tuple)) or not values:
            raise ValueError(f"{location} {operator} needs a nonempty values list")
        if all(_is_numeric_scalar(value) for value in values):
            comparable = pd.to_numeric(series, errors="coerce")
            valid = comparable.notna() & np.isfinite(comparable)
            result = comparable.isin([float(value) for value in values])
        else:
            comparable = series.astype("string")
            valid = comparable.notna()
            result = comparable.isin([str(value) for value in values])
        return valid & (result if operator == "in" else ~result)
    if operator in {"is_finite", "finite"}:
        numeric = pd.to_numeric(series, errors="coerce")
        return numeric.notna() & np.isfinite(numeric)
    if operator in {"is_zero", "zero", "nonzero"}:
        numeric = pd.to_numeric(series, errors="coerce")
        valid = numeric.notna() & np.isfinite(numeric)
        return valid & (numeric.ne(0) if operator == "nonzero" else numeric.eq(0))
    if operator in {"isna", "notna"}:
        return series.isna() if operator == "isna" else series.notna()
    if operator in {"matches", "regex"}:
        pattern = str(node.get("value", ""))
        return series.astype("string").str.fullmatch(pattern, na=False)
    raise ValueError(f"Unsupported operator {operator!r} at {location}")


def evaluate_condition(frame: pd.DataFrame, node: Any, *, location: str) -> pd.Series:
    if not isinstance(node, dict):
        raise ValueError(f"{location} must be a mapping")
    combinators = [key for key in COMBINATORS if key in node]
    if not combinators:
        return evaluate_leaf(frame, node, location).astype(bool)
    if len(combinators) != 1 or len(node) != 1:
        raise ValueError(f"{location} must contain exactly one all/any/not operator")
    operator = combinators[0]
    children = node[operator]
    if operator == "not":
        return ~evaluate_condition(frame, children, location=f"{location}.not")
    if not isinstance(children, list) or not children:
        raise ValueError(f"{location}.{operator} must be a nonempty list")
    result = pd.Series(operator == "all", index=frame.index, dtype=bool)
    for index, child in enumerate(children):
        child_mask = evaluate_condition(
            frame, child, location=f"{location}.{operator}[{index}]",
        )
        result = result & child_mask if operator == "all" else result | child_mask
    return result


def assign_gates(
    frame: pd.DataFrame,
    gates: list[Gate],
    *,
    verbose: bool = True,
) -> dict[str, pd.Series]:
    masks: dict[str, pd.Series] = {}
    combined = np.zeros(len(frame), dtype=np.int64)
    for gate in gates:
        mask = evaluate_condition(frame, gate.condition, location=f"gate[{gate.code}]")
        masks[gate.code] = mask
        combined += np.where(mask.to_numpy(dtype=bool), gate.bit_value, 0).astype(np.int64)
        if verbose:
            print(
                f"Gate {gate.short_label} [{gate.code}] ({gate.name}): {int(mask.sum()):,}/{len(frame):,} "
                f"events ({float(mask.mean()) * 100:.3f}%)"
            )
    frame["gate_code"] = pd.Series(
        [str(int(value)) for value in combined],
        index=frame.index,
        dtype="string",
    )
    return masks


def combined_name(code: str, gates: list[Gate]) -> str:
    value = int(code)
    names = [gate.name for gate in gates if value & gate.bit_value]
    return " + ".join(names) if names else "no configured gate"


def combined_short_label(code: str, gates: list[Gate]) -> str:
    value = int(code)
    labels = [gate.short_label or gate.name for gate in gates if value & gate.bit_value]
    return "+".join(labels) if labels else "None"


def write_gate_summary(
    frame: pd.DataFrame, gates: list[Gate], masks: dict[str, pd.Series], output: Path,
) -> pd.DataFrame:
    total = len(frame)
    rows: list[dict[str, Any]] = []
    for gate in gates:
        count = int(masks[gate.code].sum())
        rows.append({
            "kind": "individual",
            "gate_code": gate.code,
            "gate_name": gate.name,
            "gate_label": gate.short_label or gate.name,
            "events": count,
            "fraction": count / total if total else np.nan,
        })
    combined_counts = frame["gate_code"].value_counts().to_dict()
    for code in sorted(combined_counts, key=lambda value: int(value)):
        count = int(combined_counts[code])
        rows.append({
            "kind": "combined_exact",
            "gate_code": code,
            "gate_name": combined_name(code, gates),
            "gate_label": combined_short_label(code, gates),
            "events": count,
            "fraction": count / total if total else np.nan,
        })
    summary = pd.DataFrame(rows)
    summary.to_csv(output, index=False)
    return summary


def time_series_setting(config: dict[str, Any], available: set[str]) -> dict[str, Any] | None:
    raw = config.get("time_series", {})
    if raw is False:
        return None
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("time_series must be a YAML mapping or false")
    if not bool(raw.get("enabled", True)):
        return None
    column = str(raw.get("time_column", "datetime")).strip()
    if column not in available:
        raise ValueError(f"Time-series column absent from schema: {column}")
    try:
        window = pd.Timedelta(str(raw.get("accumulation_timespan", "1min")))
    except ValueError as exc:
        raise ValueError("Invalid time_series.accumulation_timespan") from exc
    if window <= pd.Timedelta(0):
        raise ValueError("time_series.accumulation_timespan must be positive")
    return {"column": column, "window": window}


def plot_rate_lines(
    summary: pd.DataFrame,
    lines: list[tuple[str, str]],
    output: Path,
    title: str,
) -> bool:
    plotted = [(column, label) for column, label in lines if summary[column].gt(0).any()]
    if not plotted:
        print(f"Warning: no populated rate series for {output.name}")
        return False
    fig, axis = plt.subplots(figsize=(15, 7), constrained_layout=True)
    for column, label in plotted:
        axis.plot(summary["window_start"], summary[column], marker=".", markersize=3,
                  linewidth=1.1, label=label)
    axis.set(xlabel="Time", ylabel="Event rate [Hz]", title=title)
    axis.grid(True, alpha=0.25)
    legend_columns = min(4, max(1, (len(plotted) + 5) // 6))
    axis.legend(fontsize=7, ncols=legend_columns)
    fig.autofmt_xdate()
    fig.savefig(output, dpi=160)
    plt.close(fig)
    return True


def write_gate_time_series(
    frame: pd.DataFrame,
    gates: list[Gate],
    masks: dict[str, pd.Series],
    setting: dict[str, Any],
    output_dir: Path,
    title: str,
) -> tuple[Path, int]:
    timestamps = pd.to_datetime(frame[setting["column"]], errors="coerce")
    valid = timestamps.notna()
    if not bool(valid.any()):
        raise ValueError(f"{setting['column']} contains no valid timestamps")
    events = pd.DataFrame({"second": timestamps.loc[valid].dt.floor("s")})
    individual_columns: list[tuple[str, str]] = []
    for gate in gates:
        column = f"individual_{gate.code}_events"
        events[column] = masks[gate.code].loc[valid].to_numpy(dtype=np.int8)
        individual_columns.append((column, gate.short_label or gate.name))
    combined_codes = sorted(
        frame.loc[valid, "gate_code"].dropna().astype(str).unique(),
        key=lambda code: int(code),
    )
    combined_columns: list[tuple[str, str]] = []
    gate_codes = frame.loc[valid, "gate_code"].astype(str)
    for code in combined_codes:
        column = f"combined_{code}_events"
        events[column] = gate_codes.eq(code).to_numpy(dtype=np.int8)
        combined_columns.append((column, combined_short_label(code, gates)))
    events["total_events"] = 1
    per_second = events.groupby("second", sort=True).sum(numeric_only=True)
    per_second["window_start"] = per_second.index.floor(setting["window"])
    value_columns = ["total_events", *(name for name, _ in individual_columns),
                     *(name for name, _ in combined_columns)]
    summary = per_second.groupby("window_start", sort=True)[value_columns].sum()
    summary["observed_seconds"] = per_second.groupby("window_start").size()
    summary["window_end"] = summary.index + setting["window"]
    for column in value_columns:
        summary[column.removesuffix("_events") + "_hz"] = (
            summary[column] / summary["observed_seconds"]
        )
    summary = summary.reset_index()
    ordered = ["window_start", "window_end", "observed_seconds", *value_columns,
               *(column.removesuffix("_events") + "_hz" for column in value_columns)]
    summary = summary[ordered]
    csv_path = output_dir / "gate_rates.csv"
    summary.to_csv(csv_path, index=False)
    individual_hz = [
        (column.removesuffix("_events") + "_hz", label) for column, label in individual_columns
    ]
    combined_hz = [
        (column.removesuffix("_events") + "_hz", label) for column, label in combined_columns
    ]
    written = int(plot_rate_lines(
        summary, individual_hz, output_dir / "individual_gate_rates.png",
        f"{title}\nIndividual gate rates | accumulation={setting['window']} | denominator=observed seconds",
    ))
    written += int(plot_rate_lines(
        summary, combined_hz, output_dir / "combined_exact_gate_rates.png",
        f"{title}\nExact combined-code rates | accumulation={setting['window']} | denominator=observed seconds",
    ))
    return csv_path, written


def write_streamed_gate_time_series(
    aggregates: StreamingGateAggregates,
    gates: list[Gate],
    setting: dict[str, Any],
    output_dir: Path,
    title: str,
) -> tuple[Path, int]:
    summary = gate_rate_frame(aggregates, gates)
    csv_path = output_dir / "gate_rates.csv"
    summary.to_csv(csv_path, index=False)
    individual_lines = [
        (f"individual_{gate.code}_hz", gate.short_label or gate.name)
        for gate in gates
    ]
    combined_codes = sorted(
        aggregates.combined_totals,
        key=lambda code: int(code),
    )
    combined_lines = [
        (f"combined_{code}_hz", combined_short_label(code, gates))
        for code in combined_codes
    ]
    written = int(plot_rate_lines(
        summary, individual_lines, output_dir / "individual_gate_rates.png",
        f"{title}\nIndividual gate rates | accumulation={setting['window']} | "
        "denominator=observed seconds",
    ))
    written += int(plot_rate_lines(
        summary, combined_lines, output_dir / "combined_exact_gate_rates.png",
        f"{title}\nExact combined-code rates | accumulation={setting['window']} | "
        "denominator=observed seconds",
    ))
    return csv_path, written


def one_second_burst_setting(
    config: dict[str, Any], available: set[str],
) -> dict[str, Any] | None:
    raw = config.get("one_second_burst_diagnostics", {})
    if raw is False:
        return None
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("one_second_burst_diagnostics must be a YAML mapping or false")
    if not bool(raw.get("enabled", True)):
        return None
    time_column = str(raw.get("time_column", "datetime")).strip()
    if time_column not in available:
        raise ValueError(f"One-second burst time column absent from schema: {time_column}")
    maximum_gap = int(raw.get("maximum_continuous_gap_seconds", 5))
    maximum_bins = int(raw.get("maximum_histogram_bins", 200))
    if maximum_gap < 1:
        raise ValueError("maximum_continuous_gap_seconds must be at least 1")
    if maximum_bins < 2:
        raise ValueError("maximum_histogram_bins must be at least 2")
    return {
        "time_column": time_column,
        "maximum_gap_seconds": maximum_gap,
        "maximum_histogram_bins": maximum_bins,
    }


def _integer_histogram_edges(values: np.ndarray, maximum_bins: int) -> np.ndarray:
    finite = values[np.isfinite(values)]
    if not finite.size:
        return np.array([-0.5, 0.5])
    lower, upper = float(np.min(finite)), float(np.max(finite))
    integer_span = int(round(upper - lower)) + 1
    if integer_span <= maximum_bins:
        return np.arange(np.floor(lower) - 0.5, np.ceil(upper) + 1.5, 1.0)
    return np.linspace(lower, upper, maximum_bins + 1)


def write_one_second_burst_diagnostics(
    frame: pd.DataFrame,
    gates: list[Gate],
    masks: dict[str, pd.Series],
    setting: dict[str, Any],
    output_dir: Path,
    title: str,
) -> tuple[Path, int]:
    """Plot exact one-second gate rates and forward differences without gap jumps."""
    timestamps = pd.to_datetime(frame[setting["time_column"]], errors="coerce")
    valid_time = timestamps.notna()
    if not bool(valid_time.any()):
        raise ValueError(f"{setting['time_column']} contains no valid timestamps")
    event_seconds = timestamps.loc[valid_time].dt.floor("s")
    observed_seconds = pd.DatetimeIndex(event_seconds.unique()).sort_values()
    gaps = np.diff(observed_seconds.asi8) / 1_000_000_000.0
    segment_starts = np.r_[0, np.flatnonzero(gaps > setting["maximum_gap_seconds"]) + 1]
    segment_ends = np.r_[segment_starts[1:], len(observed_seconds)]
    ranges: list[pd.DatetimeIndex] = []
    segment_ids: list[np.ndarray] = []
    for segment_id, (start_index, end_index) in enumerate(
        zip(segment_starts, segment_ends, strict=True)
    ):
        seconds = pd.date_range(
            observed_seconds[start_index], observed_seconds[end_index - 1], freq="s",
        )
        ranges.append(seconds)
        segment_ids.append(np.full(len(seconds), segment_id, dtype=np.int32))
    full_seconds = ranges[0].append(ranges[1:])
    segments = np.concatenate(segment_ids)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_rows: list[dict[str, Any]] = []

    for gate in gates:
        selected = masks[gate.code].loc[valid_time].to_numpy(dtype=np.int8)
        counts = pd.Series(selected, index=event_seconds.to_numpy()).groupby(level=0).sum()
        rates = counts.reindex(full_seconds, fill_value=0).to_numpy(dtype=np.int64)
        rate_series = pd.Series(rates)
        next_rates = rate_series.groupby(segments, sort=False).shift(-1).to_numpy(dtype=float)
        differences = next_rates - rates
        valid_difference = np.isfinite(differences)

        fig, axes = plt.subplots(
            2, 2, figsize=(19, 11), constrained_layout=True,
            gridspec_kw={"width_ratios": (3.2, 1.3)},
        )
        offset = 0
        for seconds in ranges:
            segment_slice = slice(offset, offset + len(seconds))
            axes[0, 0].plot(
                seconds, rates[segment_slice],
                linewidth=0.55, color="tab:blue", rasterized=True,
            )
            axes[1, 0].plot(
                seconds, differences[segment_slice],
                linewidth=0.55, color="tab:orange", rasterized=True,
            )
            offset += len(seconds)
        rate_edges = _integer_histogram_edges(
            rates.astype(float), setting["maximum_histogram_bins"],
        )
        difference_edges = _integer_histogram_edges(
            differences[valid_difference], setting["maximum_histogram_bins"],
        )
        axes[0, 1].hist(rates, bins=rate_edges, color="tab:blue", alpha=0.78)
        axes[1, 1].hist(
            differences[valid_difference], bins=difference_edges,
            color="tab:orange", alpha=0.78,
        )
        axes[0, 0].set(
            xlabel="Time", ylabel="Gate events per second [Hz]",
            title="Exact one-second gate rate (no accumulation)",
        )
        axes[0, 0].set_ylim(bottom=0)
        axes[0, 1].set(
            xlabel="Gate events per second [Hz]", ylabel="Number of seconds",
            title="One-second rate distribution",
        )
        axes[1, 0].axhline(0.0, color="0.25", linewidth=1.0, linestyle="--")
        axes[1, 0].set(
            xlabel="Time", ylabel="Δ rate to next second [Hz]",
            title="Forward difference: rate(t+1 s) − rate(t)",
        )
        axes[1, 1].axvline(0.0, color="0.25", linewidth=1.0, linestyle="--")
        axes[1, 1].set(
            xlabel="Δ rate to next second [Hz]", ylabel="Number of differences",
            title="One-second forward-difference distribution",
        )
        for axis in axes.flat:
            axis.grid(True, alpha=0.25)
        fig.autofmt_xdate()
        label = gate.short_label or gate.name
        fig.suptitle(
            f"{title}\nGate {label} [{gate.code}] | one-second burst diagnostic | "
            f"continuous segments={len(ranges):,}",
            fontsize=15,
            fontweight="bold",
        )
        plot_path = output_dir / f"gate_{gate.code}_one_second_burst_diagnostic.png"
        fig.savefig(plot_path, dpi=160)
        plt.close(fig)

        maximum_rate_index = int(np.argmax(rates))
        difference_indices = np.flatnonzero(valid_difference)
        if difference_indices.size:
            maximum_rise_index = int(difference_indices[np.argmax(differences[valid_difference])])
            maximum_drop_index = int(difference_indices[np.argmin(differences[valid_difference])])
            maximum_rise = float(differences[maximum_rise_index])
            maximum_drop = float(differences[maximum_drop_index])
            maximum_rise_second: Any = full_seconds[maximum_rise_index]
            maximum_drop_second: Any = full_seconds[maximum_drop_index]
        else:
            maximum_rise = maximum_drop = np.nan
            maximum_rise_second = maximum_drop_second = pd.NaT
        summary_rows.append({
            "gate_code": gate.code,
            "gate_name": gate.name,
            "gate_label": label,
            "one_second_intervals": len(rates),
            "continuous_segments": len(ranges),
            "zero_rate_seconds": int(np.count_nonzero(rates == 0)),
            "mean_rate_hz": float(np.mean(rates)),
            "standard_deviation_rate_hz": float(np.std(rates)),
            "maximum_rate_hz": int(rates[maximum_rate_index]),
            "maximum_rate_second": full_seconds[maximum_rate_index],
            "maximum_rise_to_next_second_hz": maximum_rise,
            "maximum_rise_second": maximum_rise_second,
            "maximum_drop_to_next_second_hz": maximum_drop,
            "maximum_drop_second": maximum_drop_second,
        })

    summary_path = output_dir / "one_second_burst_summary.csv"
    pd.DataFrame(summary_rows).to_csv(summary_path, index=False)
    print(
        f"One-second burst diagnostics: {len(gates)} gate(s), "
        f"{len(full_seconds):,} second(s), {len(ranges):,} continuous segment(s)"
    )
    return summary_path, len(gates)


def efficiency_time_series_setting(
    config: dict[str, Any], gates: list[Gate], available: set[str],
) -> dict[str, Any] | None:
    raw = config.get("efficiency_time_series", {})
    if raw is False:
        return None
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("efficiency_time_series must be a YAML mapping or false")
    if not bool(raw.get("enabled", True)):
        return None
    time_column = str(raw.get("time_column", "datetime")).strip()
    topology_column = str(raw.get("topology_column", "tt_task3_list")).strip()
    missing = sorted({time_column, topology_column} - available)
    if missing:
        raise ValueError(
            "Efficiency time-series columns absent from schema: " + ", ".join(missing)
        )
    try:
        window = pd.Timedelta(str(raw.get("accumulation_timespan", "10min")))
    except ValueError as exc:
        raise ValueError("Invalid efficiency_time_series.accumulation_timespan") from exc
    if window <= pd.Timedelta(0):
        raise ValueError("efficiency_time_series.accumulation_timespan must be positive")

    raw_selections = raw.get("selections", "all")
    selections: list[dict[str, str]] | None
    if isinstance(raw_selections, str) and raw_selections.strip().lower() == "all":
        selections = None
    elif isinstance(raw_selections, list) and raw_selections:
        selections = []
        seen: set[tuple[str, str]] = set()
        for index, item in enumerate(raw_selections, 1):
            if not isinstance(item, dict):
                raise ValueError(
                    f"efficiency_time_series.selections item {index} must be a mapping"
                )
            kind = str(item.get("kind", "individual")).strip().lower()
            kind = {"combined": "combined_exact", "exact": "combined_exact"}.get(
                kind, kind
            )
            location = f"efficiency_time_series.selections item {index}"
            if kind == "individual":
                gate = gate_from_short_label(
                    gates, item.get("gate_label", ""), location=location
                )
                code = gate.code
            elif kind == "combined_exact":
                code = combined_decimal_code_from_labels(
                    gates, item.get("gate_labels"), location=location + ".gate_labels"
                )
            else:
                raise ValueError(
                    "Efficiency selection kind must be individual or combined_exact: "
                    + kind
                )
            key = (kind, code)
            if key in seen:
                raise ValueError(f"Duplicate efficiency selection: {kind} {code}")
            seen.add(key)
            selections.append({
                "kind": kind,
                "code": code,
                "label": str(item.get("label", "")).strip(),
            })
    else:
        raise ValueError(
            "efficiency_time_series.selections must be all or a nonempty list"
        )
    return {
        "time_column": time_column,
        "topology_column": topology_column,
        "window": window,
        "selections": selections,
        "include_combined_zero": bool(raw.get("include_combined_zero", False)),
    }


def efficiency_selections(
    frame: pd.DataFrame,
    gates: list[Gate],
    masks: dict[str, pd.Series],
    setting: dict[str, Any],
) -> list[tuple[str, str, str, pd.Series]]:
    specs = setting["selections"]
    if specs is None:
        specs = [
            {"kind": "individual", "code": gate.code, "label": ""}
            for gate in gates
        ]
        combined_codes = sorted(
            frame["gate_code"].dropna().astype(str).unique(),
            key=lambda code: int(code),
        )
        specs.extend(
            {"kind": "combined_exact", "code": code, "label": ""}
            for code in combined_codes
            if code != "0" or setting["include_combined_zero"]
        )

    gate_names = {gate.code: gate.name for gate in gates}
    selections: list[tuple[str, str, str, pd.Series]] = []
    for spec in specs:
        kind, code = spec["kind"], spec["code"]
        if kind == "individual":
            default_label = f"{code}: {gate_names[code]}"
            mask = masks[code]
        else:
            default_label = f"{code}: {combined_name(code, gates)}"
            mask = frame["gate_code"].astype(str).eq(code)
        selections.append((kind, code, spec["label"] or default_label, mask.astype(bool)))
    return selections


def plot_efficiency_lines(
    summary: pd.DataFrame, output: Path, title: str,
) -> None:
    fig, axis = plt.subplots(figsize=(15, 7), constrained_layout=True)
    plotted = False
    for plane in range(1, 5):
        values = pd.to_numeric(summary[f"plane_{plane}_efficiency"], errors="coerce")
        if bool(values.notna().any()):
            plotted = True
            axis.plot(summary["window_start"], values, marker=".", markersize=4,
                      linewidth=1.2, label=f"Plane {plane}")
    if not plotted:
        axis.text(0.5, 0.5, "No window has a nonzero efficiency denominator",
                  ha="center", va="center", transform=axis.transAxes)
    axis.set(xlabel="Time", ylabel="Efficiency", ylim=(-0.02, 1.02), title=title)
    axis.grid(True, alpha=0.25)
    if plotted:
        axis.legend(ncols=4)
    fig.autofmt_xdate()
    fig.savefig(output, dpi=160)
    plt.close(fig)


def write_efficiency_time_series(
    frame: pd.DataFrame,
    gates: list[Gate],
    masks: dict[str, pd.Series],
    setting: dict[str, Any],
    output_dir: Path,
    title: str,
) -> tuple[Path, int]:
    time_column = setting["time_column"]
    topology_column = setting["topology_column"]
    window = setting["window"]
    timestamps = pd.to_datetime(frame[time_column], errors="coerce")
    topology_numeric = pd.to_numeric(frame[topology_column], errors="coerce")
    integer_topology = topology_numeric.where(topology_numeric.mod(1).eq(0)).astype("Int64")
    topologies = integer_topology.astype("string")
    valid_time = timestamps.notna()
    if not bool(valid_time.any()):
        raise ValueError(f"{time_column} contains no valid timestamps")
    all_windows = pd.DatetimeIndex(
        timestamps.loc[valid_time].dt.floor(window).drop_duplicates().sort_values(),
        name="window_start",
    )
    missing_topology = {1: "234", 2: "134", 3: "124", 4: "123"}
    counted_topologies = ("123", "124", "134", "234", "1234")
    rows: list[pd.DataFrame] = []
    plot_count = 0
    selections = efficiency_selections(frame, gates, masks, setting)
    for kind, code, label, gate_mask in selections:
        selected = valid_time & gate_mask
        selected_events = pd.DataFrame({
            "window_start": timestamps.loc[selected].dt.floor(window),
            "topology": topologies.loc[selected],
        })
        counts = selected_events.groupby(["window_start", "topology"]).size().unstack(fill_value=0)
        counts = counts.reindex(all_windows, fill_value=0)
        for topology in counted_topologies:
            if topology not in counts:
                counts[topology] = 0
        selection_summary = pd.DataFrame({
            "window_start": all_windows,
            "window_end": all_windows + window,
            "selection_kind": kind,
            "gate_code": code,
            "gate_name": label,
        })
        for topology in counted_topologies:
            selection_summary[f"topology_{topology}_count"] = (
                pd.to_numeric(counts[topology], errors="coerce").fillna(0).astype(np.int64).to_numpy()
            )
        detected = selection_summary["topology_1234_count"].to_numpy(dtype=float)
        for plane, missing_code in missing_topology.items():
            undetected = selection_summary[f"topology_{missing_code}_count"].to_numpy(dtype=float)
            total = detected + undetected
            selection_summary[f"plane_{plane}_undetected_count"] = undetected.astype(np.int64)
            selection_summary[f"plane_{plane}_total_count"] = total.astype(np.int64)
            selection_summary[f"plane_{plane}_efficiency"] = np.divide(
                detected, total, out=np.full(len(total), np.nan), where=total > 0,
            )
        plot_path = output_dir / f"efficiency_{kind}_{code}.png"
        plot_efficiency_lines(
            selection_summary,
            plot_path,
            f"{title} | {kind} gate {label} | accumulation={window} | "
            "efficiency = 1 - N(missing plane) / [N(1234) + N(missing plane)]",
        )
        plot_count += 1
        rows.append(selection_summary)
    summary = pd.concat(rows, ignore_index=True)
    csv_path = output_dir / "gate_plane_efficiencies.csv"
    summary.to_csv(csv_path, index=False)
    print(
        f"Efficiency time series: {len(selections)} gate selection(s), "
        f"{len(all_windows)} window(s), accumulation={window}"
    )
    return csv_path, plot_count


def write_streamed_efficiency_time_series(
    aggregates: StreamingGateAggregates,
    gates: list[Gate],
    setting: dict[str, Any],
    output_dir: Path,
    title: str,
) -> tuple[Path, int]:
    summary = efficiency_summary_frame(aggregates, gates, setting)
    plot_count = 0
    for (kind, code), selection in summary.groupby(
        ["selection_kind", "gate_code"], sort=False,
    ):
        label = str(selection["gate_name"].iloc[0])
        plot_efficiency_lines(
            selection,
            output_dir / f"efficiency_{kind}_{code}.png",
            f"{title} | {kind} gate {label} | accumulation={setting['window']} | "
            "efficiency = 1 - N(missing plane) / "
            "[N(1234) + N(missing plane)]",
        )
        plot_count += 1
    csv_path = output_dir / "gate_plane_efficiencies.csv"
    summary.to_csv(csv_path, index=False)
    print(
        f"Streaming efficiency time series: "
        f"{summary[['selection_kind', 'gate_code']].drop_duplicates().shape[0]} "
        f"gate selection(s), {len(aggregates.windows)} window(s), "
        f"accumulation={setting['window']}"
    )
    return csv_path, plot_count


def enabled_gate_comparison_setting(
    config: dict[str, Any], available: set[str], gates: list[Gate] | None = None,
) -> dict[str, Any] | None:
    raw = config.get("enabled_gate_comparison", {})
    if raw is False:
        return None
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("enabled_gate_comparison must be a YAML mapping or false")
    if not bool(raw.get("enabled", True)):
        return None
    time_column = str(raw.get("time_column", "datetime")).strip()
    topology_column = str(raw.get("topology_column", "tt_task3_list")).strip()
    missing = sorted({time_column, topology_column} - available)
    if missing:
        raise ValueError(
            "Enabled-gate comparison columns absent from schema: " + ", ".join(missing)
        )
    try:
        window = pd.Timedelta(str(raw.get("accumulation_timespan", "10min")))
    except ValueError as exc:
        raise ValueError("Invalid enabled_gate_comparison.accumulation_timespan") from exc
    if window <= pd.Timedelta(0):
        raise ValueError("enabled_gate_comparison.accumulation_timespan must be positive")
    relative_rate_half_range = float(
        raw.get("relative_corrected_rate_y_half_range", 0.5)
    )
    if not np.isfinite(relative_rate_half_range) or relative_rate_half_range <= 0:
        raise ValueError(
            "enabled_gate_comparison.relative_corrected_rate_y_half_range "
            "must be a positive number"
        )
    rate_stability_histogram_bins = int(
        raw.get("rate_stability_histogram_bins", 80)
    )
    if rate_stability_histogram_bins < 5:
        raise ValueError(
            "enabled_gate_comparison.rate_stability_histogram_bins "
            "must be at least 5"
        )
    raw_ratio = raw.get("corrected_to_all_ratio", False)
    if raw_ratio is False:
        ratio_setting = None
    else:
        if raw_ratio is None:
            raw_ratio = {}
        if not isinstance(raw_ratio, dict):
            raise ValueError(
                "enabled_gate_comparison.corrected_to_all_ratio must be a mapping or false"
            )
        if not bool(raw_ratio.get("enabled", True)):
            ratio_setting = None
        else:
            configured_gates = gates or []
            numerator_gate = gate_from_short_label(
                configured_gates, raw_ratio.get("gate_label", ""),
                location="enabled_gate_comparison.corrected_to_all_ratio.gate_label",
            )
            all_gate = gate_from_short_label(
                configured_gates, raw_ratio.get("all_gate_label", ""),
                location="enabled_gate_comparison.corrected_to_all_ratio.all_gate_label",
            )
            if numerator_gate.code == all_gate.code:
                raise ValueError(
                    "Corrected-to-ALL numerator and ALL gate labels must differ"
                )
            ratio_setting = {
                "gate_code": numerator_gate.code,
                "gate_label": numerator_gate.short_label,
                "all_gate_code": all_gate.code,
                "all_gate_label": all_gate.short_label,
            }
    return {
        "time_column": time_column,
        "topology_column": topology_column,
        "window": window,
        "relative_corrected_rate_y_half_range": relative_rate_half_range,
        "rate_stability_histogram_bins": rate_stability_histogram_bins,
        "corrected_to_all_ratio": ratio_setting,
        **efficiency_product_setting(config),
    }


def write_enabled_gate_comparison(
    frame: pd.DataFrame,
    gates: list[Gate],
    masks: dict[str, pd.Series],
    setting: dict[str, Any],
    output_dir: Path,
    title: str,
    environment_data_path: Path | None = None,
) -> tuple[Path, Path, Path, Path | None, Path, int]:
    """Overlay efficiency and rate diagnostics for every enabled individual gate."""
    time_column = setting["time_column"]
    topology_column = setting["topology_column"]
    window = setting["window"]
    timestamps = pd.to_datetime(frame[time_column], errors="coerce")
    topology_numeric = pd.to_numeric(frame[topology_column], errors="coerce")
    topologies = topology_numeric.where(topology_numeric.mod(1).eq(0)).astype("Int64").astype("string")
    valid_time = timestamps.notna()
    if not bool(valid_time.any()):
        raise ValueError(f"{time_column} contains no valid timestamps")
    seconds = timestamps.loc[valid_time].dt.floor("s")
    all_windows = pd.DatetimeIndex(
        timestamps.loc[valid_time].dt.floor(window).drop_duplicates().sort_values(),
        name="window_start",
    )
    exposure = pd.DataFrame({
        "window_start": seconds.dt.floor(window),
        "second": seconds,
    }).groupby("window_start")["second"].nunique().reindex(all_windows, fill_value=0)

    counted_topologies = ("123", "124", "134", "234", "1234")
    missing_topology = {1: "234", 2: "134", 3: "124", 4: "123"}
    rows: list[pd.DataFrame] = []
    for gate in gates:
        selected = valid_time & masks[gate.code]
        selected_windows = timestamps.loc[selected].dt.floor(window)
        gate_event_counts = selected_windows.value_counts(sort=False).reindex(
            all_windows, fill_value=0,
        )
        selected_events = pd.DataFrame({
            "window_start": selected_windows,
            "topology": topologies.loc[selected],
        })
        counts = selected_events.groupby(["window_start", "topology"]).size().unstack(fill_value=0)
        counts = counts.reindex(all_windows, fill_value=0)
        for topology in counted_topologies:
            if topology not in counts:
                counts[topology] = 0
        summary = pd.DataFrame({
            "window_start": all_windows,
            "window_end": all_windows + window,
            "gate_code": gate.code,
            "gate_name": gate.name,
            "gate_label": gate.short_label or gate.name,
            "observed_seconds": exposure.to_numpy(dtype=np.int64),
            "gate_event_count": gate_event_counts.to_numpy(dtype=np.int64),
        })
        for topology in counted_topologies:
            summary[f"topology_{topology}_count"] = (
                pd.to_numeric(counts[topology], errors="coerce")
                .fillna(0).astype(np.int64).to_numpy()
            )
        detected = summary["topology_1234_count"].to_numpy(dtype=float)
        for plane, missing_code in missing_topology.items():
            undetected = summary[f"topology_{missing_code}_count"].to_numpy(dtype=float)
            denominator = detected + undetected
            summary[f"plane_{plane}_efficiency"] = np.divide(
                detected, denominator,
                out=np.full(len(denominator), np.nan), where=denominator > 0,
            )
        product_planes = setting.get("efficiency_product_planes", (1, 2, 3, 4))
        summary["efficiency_product"] = efficiency_product_from_frame(
            summary, product_planes, column_template="plane_{plane}_efficiency",
        )
        summary["efficiency_product_mode"] = setting.get("efficiency_product_mode", "all_planes")
        summary["efficiency_product_plane_numbers"] = ",".join(
            str(plane) for plane in product_planes
        )
        observed_seconds = summary["observed_seconds"].to_numpy(dtype=float)
        summary["total_gate_rate_hz"] = np.divide(
            summary["gate_event_count"].to_numpy(dtype=float), observed_seconds,
            out=np.full(len(observed_seconds), np.nan), where=observed_seconds > 0,
        )
        summary["topology_1234_rate_hz"] = np.divide(
            detected, observed_seconds,
            out=np.full(len(observed_seconds), np.nan), where=observed_seconds > 0,
        )
        efficiency_product = summary["efficiency_product"].to_numpy(dtype=float)
        rate_1234 = summary["topology_1234_rate_hz"].to_numpy(dtype=float)
        summary["corrected_1234_rate_hz"] = np.divide(
            rate_1234, efficiency_product,
            out=np.full(len(rate_1234), np.nan),
            where=np.isfinite(efficiency_product) & (efficiency_product > 0),
        )
        rows.append(summary)

    comparison = pd.concat(rows, ignore_index=True)
    return _write_enabled_gate_comparison_outputs(
        comparison, gates, setting, output_dir, title, environment_data_path,
    )


def write_streamed_enabled_gate_comparison(
    aggregates: StreamingGateAggregates,
    gates: list[Gate],
    setting: dict[str, Any],
    output_dir: Path,
    title: str,
    environment_data_path: Path | None = None,
) -> tuple[Path, Path, Path, Path | None, Path, int]:
    comparison = enabled_gate_comparison_frame(
        aggregates, gates,
        setting.get("efficiency_product_planes", (1, 2, 3, 4)),
        setting.get("efficiency_product_mode", "all_planes"),
    )
    return _write_enabled_gate_comparison_outputs(
        comparison, gates, setting, output_dir, title, environment_data_path,
    )


def _fit_gaussian(values: pd.Series) -> tuple[np.ndarray, float, float]:
    numeric = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float)
    finite = numeric[np.isfinite(numeric)]
    if finite.size < 2:
        return finite, np.nan, np.nan
    try:
        mean, sigma = norm.fit(finite)
    except (RuntimeError, TypeError, ValueError, FloatingPointError):
        return finite, np.nan, np.nan
    return finite, float(mean), float(sigma)


def write_gate_rate_stability_histograms(
    comparison: pd.DataFrame,
    gates: list[Gate],
    output_dir: Path,
    title: str,
    *,
    bins: int = 80,
) -> Path:
    """Compare uncorrected/corrected 1234-rate distributions and Gaussian widths."""
    path = output_dir / "enabled_gate_rate_stability_histograms.png"
    figure, axes = plt.subplots(
        1, 2, figsize=(19, 8), sharey=False, constrained_layout=True,
    )
    colors = plt.get_cmap("tab10").colors
    panels = (
        (
            "topology_1234_rate_hz",
            "Uncorrected 1234 rate [Hz]",
            "Uncorrected 1234-rate stability",
        ),
        (
            "corrected_1234_rate_hz",
            "Efficiency-corrected 1234 rate [Hz]",
            "Corrected 1234-rate stability",
        ),
    )
    for axis, (column, xlabel, panel_title) in zip(axes, panels, strict=True):
        plotted = 0
        for gate_index, gate in enumerate(gates):
            gate_rows = comparison.loc[comparison["gate_code"].eq(gate.code)]
            values, mean, sigma = _fit_gaussian(gate_rows[column])
            if not values.size:
                continue
            color = colors[gate_index % len(colors)]
            relative_sigma = (
                100.0 * sigma / mean
                if (
                    np.isfinite(mean)
                    and mean > 0.0
                    and np.isfinite(sigma)
                )
                else np.nan
            )
            deviation_label = (
                f"σ/μ={relative_sigma:.2f}%"
                if np.isfinite(relative_sigma)
                else "σ/μ unavailable"
            )
            label = (
                f"{gate.short_label or gate.name} [{gate.code}] "
                f"({deviation_label})"
            )
            axis.hist(
                values,
                bins=bins,
                density=True,
                histtype="step",
                linewidth=1.35,
                color=color,
                alpha=0.9,
                label=label,
            )
            if np.isfinite(mean) and np.isfinite(sigma) and sigma > 0:
                lower = max(float(np.min(values)), mean - 4.0 * sigma)
                upper = min(float(np.max(values)), mean + 4.0 * sigma)
                if upper > lower:
                    x_values = np.linspace(lower, upper, 300)
                    axis.plot(
                        x_values,
                        norm.pdf(x_values, loc=mean, scale=sigma),
                        color=color,
                        linewidth=1.0,
                        linestyle="--",
                    )
            plotted += 1
        axis.set(
            xlabel=xlabel,
            ylabel="Probability density",
            title=f"{panel_title} | Gaussian maximum-likelihood fits",
            yscale="log",
        )
        axis.grid(True, alpha=0.25)
        if plotted:
            axis.legend(fontsize=7, ncols=2)
        else:
            axis.text(
                0.5, 0.5, "No finite rate values",
                ha="center", va="center", transform=axis.transAxes,
            )
    figure.suptitle(
        f"{title}\nGate-rate stability distributions | bins={bins} | "
        "legend relative deviation σ/μ from Gaussian fit",
        fontsize=14,
    )
    figure.savefig(path, dpi=160)
    plt.close(figure)
    return path


def write_charge_cluster_size_study(
    histograms: StreamingChargeClusterHistograms,
    gates: list[Gate],
    output_dir: Path,
    title: str,
) -> list[tuple[Path, Path]]:
    """Write one four-plane charge-distribution figure per enabled gate."""
    output_dir.mkdir(parents=True, exist_ok=True)
    edges = histograms.edges
    colors = plt.get_cmap("tab10").colors
    outputs: list[tuple[Path, Path]] = []
    for gate in gates:
        plot_path = (
            output_dir
            / f"gate_{gate.code}_plane_total_charge_by_cluster_size.png"
        )
        csv_path = (
            output_dir
            / f"gate_{gate.code}_plane_total_charge_by_cluster_size.csv"
        )
        figure, axes = plt.subplots(
            4, 1, figsize=(16, 16), sharex=True, constrained_layout=True,
        )
        rows: list[dict[str, Any]] = []
        for plane, axis in enumerate(axes, 1):
            for cluster_size in range(1, 5):
                key = (gate.code, plane, cluster_size)
                counts = histograms.counts.get(
                    key, np.zeros(len(edges) - 1, dtype=np.int64),
                )
                underflow = int(histograms.underflow.get(key, 0))
                overflow = int(histograms.overflow.get(key, 0))
                in_range = int(counts.sum())
                axis.stairs(
                    counts,
                    edges,
                    color=colors[(cluster_size - 1) % len(colors)],
                    linewidth=1.35,
                    fill=False,
                    alpha=0.95,
                    label=(
                        f"Cluster size {cluster_size} "
                        f"(n={in_range:,}, below={underflow:,}, above={overflow:,})"
                    ),
                )
                for bin_index, count in enumerate(counts):
                    rows.append({
                        "gate_code": gate.code,
                        "gate_name": gate.name,
                        "gate_short_label": gate.short_label,
                        "plane": plane,
                        "cluster_size": cluster_size,
                        "bin_index": bin_index,
                        "charge_lower": float(edges[bin_index]),
                        "charge_upper": float(edges[bin_index + 1]),
                        "events": int(count),
                        "underflow_events": underflow,
                        "overflow_events": overflow,
                    })
            axis.set(
                ylabel="Events",
                title=f"Plane {plane}: total charge by cluster size",
                yscale="log",
                xlim=(float(edges[0]), float(edges[-1])),
            )
            axis.grid(True, alpha=0.25)
            axis.legend(fontsize=8, ncols=2)
        axes[-1].set_xlabel("Total plane charge")
        figure.suptitle(
            f"{title}\nGate {gate.short_label or gate.name} [{gate.code}] | "
            "plane total-charge distributions | shared charge axis | "
            "cluster sizes 1–4 shown as step histograms | "
            "logarithmic event counts",
            fontsize=14,
        )
        figure.savefig(plot_path, dpi=160)
        plt.close(figure)
        pd.DataFrame(rows).to_csv(csv_path, index=False)
        outputs.append((plot_path, csv_path))
    return outputs


def write_plane_xy_histograms(
    histograms: StreamingPlaneXYHistograms,
    gates: list[Gate],
    output_dir: Path,
    title: str,
) -> list[tuple[Path, Path]]:
    """Write one four-plane projected X/Y histogram figure per enabled gate."""
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[tuple[Path, Path]] = []
    shape = (len(histograms.x_edges) - 1, len(histograms.y_edges) - 1)
    for gate in gates:
        plot_path = output_dir / f"gate_{gate.code}_plane_xy_histograms.png"
        csv_path = output_dir / f"gate_{gate.code}_plane_xy_histograms.csv"
        plane_counts = [
            histograms.counts.get(
                (gate.code, plane), np.zeros(shape, dtype=np.int64),
            )
            for plane in range(1, 5)
        ]
        maximum = max((int(counts.max()) for counts in plane_counts), default=0)
        norm = LogNorm(vmin=1, vmax=max(1.01, float(maximum)))
        figure, axes = plt.subplots(
            2, 2, figsize=(14, 12), sharex=True, sharey=True,
            constrained_layout=True,
        )
        rows: list[dict[str, Any]] = []
        mesh = None
        for plane, (axis, counts) in enumerate(
            zip(axes.flat, plane_counts, strict=True), 1,
        ):
            mesh = axis.pcolormesh(
                histograms.x_edges,
                histograms.y_edges,
                np.ma.masked_less_equal(counts.T, 0),
                cmap="viridis",
                norm=norm,
                shading="flat",
            )
            outside = int(histograms.outside.get((gate.code, plane), 0))
            axis.set(
                title=(
                    f"Plane {plane} | in range={int(counts.sum()):,} | "
                    f"outside={outside:,}"
                ),
                aspect="equal",
                xlim=(
                    float(histograms.x_edges[0]),
                    float(histograms.x_edges[-1]),
                ),
                ylim=(
                    float(histograms.y_edges[0]),
                    float(histograms.y_edges[-1]),
                ),
            )
            axis.grid(False)
            for x_index in range(shape[0]):
                for y_index in range(shape[1]):
                    rows.append({
                        "gate_code": gate.code,
                        "gate_name": gate.name,
                        "gate_short_label": gate.short_label,
                        "plane": plane,
                        "x_lower": float(histograms.x_edges[x_index]),
                        "x_upper": float(histograms.x_edges[x_index + 1]),
                        "y_lower": float(histograms.y_edges[y_index]),
                        "y_upper": float(histograms.y_edges[y_index + 1]),
                        "events": int(counts[x_index, y_index]),
                        "outside_events": outside,
                    })
        for axis in axes[:, 0]:
            axis.set_ylabel("Projected Y at plane")
        for axis in axes[-1, :]:
            axis.set_xlabel("Projected X at plane")
        if mesh is not None:
            figure.colorbar(
                mesh, ax=list(axes.flat), label="Events per X/Y bin (log scale)",
            )
        figure.suptitle(
            f"{title}\nGate {gate.short_label or gate.name} [{gate.code}] | "
            "projected track X versus Y by plane",
            fontsize=14,
        )
        figure.savefig(plot_path, dpi=160)
        plt.close(figure)
        pd.DataFrame(rows).to_csv(csv_path, index=False)
        outputs.append((plot_path, csv_path))
    return outputs


def write_plane_efficiency_maps(
    maps: StreamingPlaneEfficiencyMaps,
    gates: list[Gate],
    output_dir: Path,
    title: str,
) -> list[tuple[Path, Path, Path, Path]]:
    """Write detected, missing, and efficiency maps for every enabled gate."""
    output_dir.mkdir(parents=True, exist_ok=True)
    missing_topologies = {1: "234", 2: "134", 3: "124", 4: "123"}
    shape = (len(maps.x_edges) - 1, len(maps.y_edges) - 1)
    outputs: list[tuple[Path, Path, Path, Path]] = []

    def count_figure(
        counts_by_plane: list[np.ndarray],
        path: Path,
        gate: Gate,
        heading: str,
        panel_titles: list[str],
    ) -> None:
        maximum = max(
            (int(counts.max()) for counts in counts_by_plane), default=0,
        )
        norm = LogNorm(vmin=1, vmax=max(1.01, float(maximum)))
        figure, axes = plt.subplots(
            2, 2, figsize=(14, 12), sharex=True, sharey=True,
            constrained_layout=True,
        )
        mesh = None
        for axis, counts, panel_title in zip(
            axes.flat, counts_by_plane, panel_titles, strict=True,
        ):
            mesh = axis.pcolormesh(
                maps.x_edges,
                maps.y_edges,
                np.ma.masked_less_equal(counts.T, 0),
                cmap="viridis",
                norm=norm,
                shading="flat",
            )
            axis.set(
                title=panel_title,
                aspect="equal",
                xlim=(float(maps.x_edges[0]), float(maps.x_edges[-1])),
                ylim=(float(maps.y_edges[0]), float(maps.y_edges[-1])),
            )
        for axis in axes[:, 0]:
            axis.set_ylabel("Projected Y at plane")
        for axis in axes[-1, :]:
            axis.set_xlabel("Projected X at plane")
        if mesh is not None:
            figure.colorbar(
                mesh, ax=list(axes.flat),
                label="Events per X/Y bin (log scale)",
            )
        figure.suptitle(
            f"{title}\nGate {gate.short_label or gate.name} [{gate.code}] | "
            f"{heading}",
            fontsize=14,
        )
        figure.savefig(path, dpi=160)
        plt.close(figure)

    for gate in gates:
        detected_path = output_dir / f"gate_{gate.code}_1234_positions.png"
        missing_path = output_dir / f"gate_{gate.code}_missing_positions.png"
        efficiency_path = output_dir / f"gate_{gate.code}_efficiency.png"
        csv_path = output_dir / f"gate_{gate.code}_efficiency_plane.csv"
        detected_by_plane = [
            maps.detected_counts.get(
                (gate.code, plane), np.zeros(shape, dtype=np.int64),
            )
            for plane in range(1, 5)
        ]
        missing_by_plane = [
            maps.missing_counts.get(
                (gate.code, plane), np.zeros(shape, dtype=np.int64),
            )
            for plane in range(1, 5)
        ]
        count_figure(
            detected_by_plane,
            detected_path,
            gate,
            "exact topology 1234 projected positions",
            [
                f"Plane {plane} | topology 1234 | "
                f"n={int(detected_by_plane[plane - 1].sum()):,} | "
                f"outside={int(maps.detected_outside.get((gate.code, plane), 0)):,}"
                for plane in range(1, 5)
            ],
        )
        count_figure(
            missing_by_plane,
            missing_path,
            gate,
            "missing-plane projected positions",
            [
                f"Plane {plane} | topology {missing_topologies[plane]} | "
                f"n={int(missing_by_plane[plane - 1].sum()):,} | "
                f"outside={int(maps.missing_outside.get((gate.code, plane), 0)):,}"
                for plane in range(1, 5)
            ],
        )

        figure, axes = plt.subplots(
            2, 2, figsize=(14, 12), sharex=True, sharey=True,
            constrained_layout=True,
        )
        rows: list[dict[str, Any]] = []
        mesh = None
        for plane, (axis, detected, missing) in enumerate(
            zip(
                axes.flat,
                detected_by_plane,
                missing_by_plane,
                strict=True,
            ),
            1,
        ):
            denominator = detected + missing
            efficiency = np.divide(
                detected,
                denominator,
                out=np.full(shape, np.nan),
                where=denominator > 0,
            )
            mesh = axis.pcolormesh(
                maps.x_edges,
                maps.y_edges,
                np.ma.masked_invalid(efficiency.T),
                cmap="viridis",
                vmin=0.0,
                vmax=1.0,
                shading="flat",
            )
            detected_total = int(detected.sum())
            missing_total = int(missing.sum())
            integrated = (
                detected_total / (detected_total + missing_total)
                if detected_total + missing_total
                else np.nan
            )
            axis.set(
                title=(
                    f"Plane {plane} | ε={integrated:.4f} | "
                    f"N1234={detected_total:,} | "
                    f"N{missing_topologies[plane]}={missing_total:,}"
                ),
                aspect="equal",
                xlim=(float(maps.x_edges[0]), float(maps.x_edges[-1])),
                ylim=(float(maps.y_edges[0]), float(maps.y_edges[-1])),
            )
            for x_index in range(shape[0]):
                for y_index in range(shape[1]):
                    rows.append({
                        "gate_code": gate.code,
                        "gate_name": gate.name,
                        "gate_short_label": gate.short_label,
                        "plane": plane,
                        "missing_topology": missing_topologies[plane],
                        "x_lower": float(maps.x_edges[x_index]),
                        "x_upper": float(maps.x_edges[x_index + 1]),
                        "y_lower": float(maps.y_edges[y_index]),
                        "y_upper": float(maps.y_edges[y_index + 1]),
                        "topology_1234_count": int(
                            detected[x_index, y_index]
                        ),
                        "missing_topology_count": int(
                            missing[x_index, y_index]
                        ),
                        "efficiency": float(
                            efficiency[x_index, y_index]
                        ),
                        "topology_1234_outside": int(
                            maps.detected_outside.get(
                                (gate.code, plane), 0,
                            )
                        ),
                        "missing_topology_outside": int(
                            maps.missing_outside.get(
                                (gate.code, plane), 0,
                            )
                        ),
                    })
        for axis in axes[:, 0]:
            axis.set_ylabel("Projected Y at plane")
        for axis in axes[-1, :]:
            axis.set_xlabel("Projected X at plane")
        if mesh is not None:
            figure.colorbar(
                mesh, ax=list(axes.flat),
                label="Plane efficiency N1234 / (N1234 + Nmissing)",
            )
        figure.suptitle(
            f"{title}\nGate {gate.short_label or gate.name} [{gate.code}] | "
            "spatial plane-efficiency maps",
            fontsize=14,
        )
        figure.savefig(efficiency_path, dpi=160)
        plt.close(figure)
        pd.DataFrame(rows).to_csv(csv_path, index=False)
        outputs.append(
            (detected_path, missing_path, efficiency_path, csv_path)
        )
    return outputs


def _write_enabled_gate_comparison_outputs(
    comparison: pd.DataFrame,
    gates: list[Gate],
    setting: dict[str, Any],
    output_dir: Path,
    title: str,
    environment_data_path: Path | None,
) -> tuple[Path, Path, Path, Path | None, Path, int]:
    window = setting["window"]
    relative_rate_half_range = setting.get(
        "relative_corrected_rate_y_half_range", 0.5,
    )
    comparison, normalized_path = write_corrected_rate_reduced_field_comparison(
        comparison, window, environment_data_path, output_dir, title,
        relative_rate_half_range,
    )
    colors = plt.get_cmap("tab10").colors

    efficiency_path = output_dir / "enabled_gate_plane_efficiencies.png"
    efficiency_figure, efficiency_axes = plt.subplots(
        4, 1, figsize=(16, 14), sharex=True, constrained_layout=True,
    )
    for gate_index, gate in enumerate(gates):
        gate_rows = comparison.loc[comparison["gate_code"].eq(gate.code)]
        label = f"{gate.short_label or gate.name} [{gate.code}]"
        for plane, axis in enumerate(efficiency_axes, 1):
            axis.plot(
                gate_rows["window_start"], gate_rows[f"plane_{plane}_efficiency"],
                color=colors[gate_index % len(colors)], marker=".", markersize=3,
                linewidth=1.1, label=label,
            )
    for plane, axis in enumerate(efficiency_axes, 1):
        axis.set(ylabel=f"Plane {plane}\nefficiency", ylim=(-0.02, 1.02))
        axis.grid(True, alpha=0.25)
    efficiency_axes[0].legend(ncols=min(4, len(gates)), fontsize=8)
    efficiency_axes[-1].set_xlabel("Time")
    efficiency_figure.suptitle(
        f"{title}\nPlane efficiency by enabled gate | accumulation={window}",
        fontsize=14,
    )
    efficiency_figure.autofmt_xdate()
    efficiency_figure.savefig(efficiency_path, dpi=160)
    plt.close(efficiency_figure)

    metrics_path = output_dir / "enabled_gate_rate_efficiency_product.png"
    metrics_figure, metrics_axes = plt.subplots(
        4, 1, figsize=(16, 15), sharex=True, constrained_layout=True,
    )
    product_label = setting.get(
        "efficiency_product_label", "all four plane efficiencies",
    )
    metric_specs = (
        ("total_gate_rate_hz", "Total gate rate [Hz]", "Total selected-event rate per enabled gate"),
        (
            "efficiency_product", "Efficiency product",
            f"Product of {product_label}",
        ),
        (
            "corrected_1234_rate_hz", "Corrected 1234 rate [Hz]",
            "1234 rate × (1 / efficiency product)",
        ),
        (
            "relative_corrected_1234_rate", "Relative corrected rate",
            "Corrected 1234 rate / per-gate mean corrected rate",
        ),
    )
    for gate_index, gate in enumerate(gates):
        gate_rows = comparison.loc[comparison["gate_code"].eq(gate.code)]
        label = f"{gate.short_label or gate.name} [{gate.code}]"
        for axis, (column, _, _) in zip(metrics_axes, metric_specs, strict=True):
            axis.plot(
                gate_rows["window_start"], gate_rows[column],
                color=colors[gate_index % len(colors)], marker=".", markersize=3,
                linestyle="none", label=label,
            )
    for axis, (_, ylabel, axis_title) in zip(metrics_axes, metric_specs, strict=True):
        axis.set(ylabel=ylabel, title=axis_title)
        axis.grid(True, alpha=0.25)
    metrics_axes[-1].axhline(
        1.0, color="0.25", linewidth=1.0, linestyle="--", label="Per-gate mean",
    )
    metrics_axes[-1].set_ylim(
        1.0 - relative_rate_half_range,
        1.0 + relative_rate_half_range,
    )
    metrics_axes[0].legend(ncols=min(4, len(gates)), fontsize=8)
    metrics_axes[-1].set_xlabel("Time")
    metrics_figure.suptitle(
        f"{title}\nEnabled-gate comparison | accumulation={window} | "
        "rate denominator=observed timestamp-seconds",
        fontsize=14,
    )
    metrics_figure.autofmt_xdate()
    metrics_figure.savefig(metrics_path, dpi=160)
    plt.close(metrics_figure)

    stability_path = write_gate_rate_stability_histograms(
        comparison,
        gates,
        output_dir,
        title,
        bins=int(setting.get("rate_stability_histogram_bins", 80)),
    )
    print(f"Enabled-gate rate-stability histograms: {stability_path}")

    ratio_path: Path | None = None
    if setting.get("corrected_to_all_ratio") is not None:
        ratio_path, _ = write_corrected_gate_to_all_ratio(
            comparison, setting["corrected_to_all_ratio"], output_dir, title,
        )
    csv_path = output_dir / "enabled_gate_comparison.csv"
    comparison.to_csv(csv_path, index=False)
    print(
        f"Enabled-gate comparison: {len(gates)} gate(s), "
        f"{comparison['window_start'].nunique()} window(s), "
        f"accumulation={window}"
    )
    return (
        efficiency_path, metrics_path, normalized_path, ratio_path, csv_path,
        4 + int(ratio_path is not None),
    )


def write_corrected_rate_reduced_field_comparison(
    comparison: pd.DataFrame,
    window: pd.Timedelta,
    environment_data_path: Path | None,
    output_dir: Path,
    title: str,
    y_half_range: float = 0.5,
) -> tuple[pd.DataFrame, Path]:
    """Compare relative uncorrected/corrected gate rates with synchronized E/N."""
    result = comparison.copy()
    result["window_start"] = pd.to_datetime(result["window_start"], errors="coerce")
    uncorrected = pd.to_numeric(result["topology_1234_rate_hz"], errors="coerce")
    finite_uncorrected = uncorrected.where(np.isfinite(uncorrected))
    uncorrected_reference = finite_uncorrected.groupby(
        result["gate_code"]
    ).transform("mean")
    result["uncorrected_1234_rate_reference_hz"] = uncorrected_reference
    result["relative_uncorrected_1234_rate"] = np.divide(
        uncorrected.to_numpy(dtype=float),
        uncorrected_reference.to_numpy(dtype=float),
        out=np.full(len(result), np.nan),
        where=np.isfinite(uncorrected_reference.to_numpy(dtype=float))
        & (uncorrected_reference.to_numpy(dtype=float) > 0),
    )
    corrected = pd.to_numeric(result["corrected_1234_rate_hz"], errors="coerce")
    finite_corrected = corrected.where(np.isfinite(corrected))
    reference = finite_corrected.groupby(result["gate_code"]).transform("mean")
    result["corrected_1234_rate_reference_hz"] = reference
    result["relative_corrected_1234_rate"] = np.divide(
        corrected.to_numpy(dtype=float), reference.to_numpy(dtype=float),
        out=np.full(len(result), np.nan),
        where=np.isfinite(reference.to_numpy(dtype=float))
        & (reference.to_numpy(dtype=float) > 0),
    )

    reduced_field_by_window = pd.Series(dtype=float, name="reduced_field_td")
    if environment_data_path is not None and environment_data_path.exists():
        environment = pd.read_csv(environment_data_path, low_memory=False)
        if {"Time", REDUCED_FIELD_COLUMN}.issubset(environment.columns):
            environment["Time"] = pd.to_datetime(environment["Time"], errors="coerce")
            environment[REDUCED_FIELD_COLUMN] = pd.to_numeric(
                environment[REDUCED_FIELD_COLUMN], errors="coerce",
            )
            valid_environment = (
                environment["Time"].notna()
                & np.isfinite(environment[REDUCED_FIELD_COLUMN])
            )
            synchronized = environment.loc[
                valid_environment, ["Time", REDUCED_FIELD_COLUMN]
            ].copy()
            synchronized["window_start"] = synchronized["Time"].dt.floor(window)
            reduced_field_by_window = synchronized.groupby("window_start")[
                REDUCED_FIELD_COLUMN
            ].mean().rename("reduced_field_td")
    result = result.merge(
        reduced_field_by_window, how="left", left_on="window_start", right_index=True,
        validate="many_to_one",
    )

    plot_path = output_dir / "enabled_gate_relative_corrected_rate_vs_reduced_field.png"
    figure, axes = plt.subplots(
        2, 2, figsize=(20, 15), constrained_layout=True,
        gridspec_kw={"width_ratios": (1.35, 1.0)},
    )
    colors = plt.get_cmap("tab10").colors
    gate_codes = list(result["gate_code"].drop_duplicates())
    row_specs = (
        (
            "relative_uncorrected_1234_rate", "Relative uncorrected 1234 rate",
            "R1234 / ⟨R1234⟩", "Mean-normalized uncorrected 1234 rate",
            "Relative uncorrected rate versus reduced electric field",
        ),
        (
            "relative_corrected_1234_rate", "Relative corrected 1234 rate",
            "Rcorr / ⟨Rcorr⟩", "Mean-normalized efficiency-corrected 1234 rate",
            "Relative corrected rate versus reduced electric field",
        ),
    )
    scatter_points = [0, 0]
    for gate_index, gate_code in enumerate(gate_codes):
        gate_rows = result.loc[result["gate_code"].eq(gate_code)].sort_values(
            "window_start"
        )
        gate_label = str(gate_rows["gate_label"].iloc[0])
        label = f"{gate_label} [{gate_code}]"
        color = colors[gate_index % len(colors)]
        for row_index, (column, _, _, _, _) in enumerate(row_specs):
            time_axis, scatter_axis = axes[row_index]
            time_axis.scatter(
                gate_rows["window_start"], gate_rows[column],
                s=12, color=color, marker="o", edgecolors="none", alpha=0.70,
                label=label, rasterized=True,
            )
            valid_scatter = (
                np.isfinite(gate_rows["reduced_field_td"])
                & np.isfinite(gate_rows[column])
            )
            if bool(valid_scatter.any()):
                scatter_points[row_index] += int(valid_scatter.sum())
                scatter_axis.scatter(
                    gate_rows.loc[valid_scatter, "reduced_field_td"],
                    gate_rows.loc[valid_scatter, column],
                    s=22, color=color, edgecolors="none", alpha=0.52,
                    label=f"{label} (n={int(valid_scatter.sum()):,})",
                    rasterized=True,
                )
    for row_index, (_, ylabel, formula, time_title, scatter_title) in enumerate(
        row_specs
    ):
        time_axis, scatter_axis = axes[row_index]
        time_axis.set(
            xlabel="Time", ylabel=f"{ylabel}\n({formula})", title=time_title,
        )
        scatter_axis.set(
            xlabel="Reduced electric field E/N [Td]",
            ylabel=f"{ylabel}\n({formula})", title=scatter_title,
        )
        time_axis.legend(loc="best", fontsize=8, ncols=2)
        if scatter_points[row_index]:
            scatter_axis.legend(loc="best", fontsize=8, ncols=2)
        else:
            scatter_axis.text(
                0.5, 0.5, "No synchronized reduced-field/rate data",
                transform=scatter_axis.transAxes, ha="center", va="center",
                color="0.4",
            )
    for axis in axes.flat:
        axis.axhline(1.0, color="0.35", linewidth=1.1, linestyle="--")
        axis.grid(True, alpha=0.25)
        axis.set_ylim(1.0 - y_half_range, 1.0 + y_half_range)
    figure.suptitle(
        f"{title}\nEnabled-gate relative uncorrected and corrected 1234 rates | "
        f"accumulation={window} | "
        "E/N averaged in matching windows",
        fontsize=14,
    )
    figure.autofmt_xdate()
    figure.savefig(plot_path, dpi=160)
    plt.close(figure)
    return result, plot_path


def write_corrected_gate_to_all_ratio(
    comparison: pd.DataFrame,
    setting: dict[str, str],
    output_dir: Path,
    title: str,
) -> tuple[Path, Path]:
    """Plot corrected selected-gate rate divided by the total ALL-gate rate."""
    numerator_code = setting["gate_code"]
    all_code = setting["all_gate_code"]
    numerator = comparison.loc[
        comparison["gate_code"].astype(str).eq(numerator_code),
        ["window_start", "window_end", "gate_label", "corrected_1234_rate_hz"],
    ].copy()
    denominator = comparison.loc[
        comparison["gate_code"].astype(str).eq(all_code),
        ["window_start", "total_gate_rate_hz"],
    ].copy().rename(columns={"total_gate_rate_hz": "all_gate_rate_hz"})
    ratio = numerator.merge(
        denominator, on="window_start", how="left", validate="one_to_one",
    )
    corrected = pd.to_numeric(ratio["corrected_1234_rate_hz"], errors="coerce")
    all_rate = pd.to_numeric(ratio["all_gate_rate_hz"], errors="coerce")
    ratio["corrected_gate_to_all_rate_ratio"] = np.divide(
        corrected.to_numpy(dtype=float), all_rate.to_numpy(dtype=float),
        out=np.full(len(ratio), np.nan),
        where=np.isfinite(all_rate.to_numpy(dtype=float))
        & (all_rate.to_numpy(dtype=float) > 0),
    )
    ratio.insert(2, "gate_code", numerator_code)
    ratio.insert(3, "all_gate_code", all_code)
    ratio_csv_path = output_dir / "corrected_gate_to_all_rate_ratio.csv"
    ratio.to_csv(ratio_csv_path, index=False)

    is_mingo00 = title.split("|", 1)[0].strip().upper() == "MINGO00"
    plot_path = output_dir / (
        "scale_factor.png" if is_mingo00
        else "corrected_gate_to_all_rate_ratio.png"
    )
    figure, axis = plt.subplots(figsize=(16, 6.5), constrained_layout=True)
    valid = np.isfinite(ratio["corrected_gate_to_all_rate_ratio"])
    gate_label = (
        str(ratio["gate_label"].dropna().iloc[0])
        if bool(ratio["gate_label"].notna().any()) else numerator_code
    )
    axis.plot(
        pd.to_datetime(ratio.loc[valid, "window_start"], errors="coerce"),
        ratio.loc[valid, "corrected_gate_to_all_rate_ratio"],
        color="tab:blue", marker=".", markersize=4, linewidth=1.2,
        label=(
            f"corrected {gate_label} [{numerator_code}] / "
            f"ALL [{all_code}] total rate"
        ),
    )
    axis.set(
        xlabel="Time",
        ylabel="Corrected gate rate / ALL gate rate",
        title="SCALE FACTOR" if is_mingo00 else "Corrected gate rate / ALL gate rate",
    )
    axis.set_ylim(bottom=0)
    axis.grid(True, alpha=0.25)
    if bool(valid.any()):
        axis.legend(loc="best", fontsize=9)
    else:
        axis.text(
            0.5, 0.5, "No valid corrected-gate/ALL-rate ratios",
            transform=axis.transAxes, ha="center", va="center", color="0.4",
        )
    figure.suptitle(
        f"{title}\n" + (
            "SCALE FACTOR" if is_mingo00
            else "Enabled-gate corrected-to-ALL rate ratio"
        ),
        fontsize=15,
        fontweight="bold" if is_mingo00 else "normal",
    )
    figure.autofmt_xdate()
    figure.savefig(plot_path, dpi=160)
    plt.close(figure)
    return plot_path, ratio_csv_path


def environment_frequency_efficiency_setting(
    config: dict[str, Any],
) -> dict[str, Any] | None:
    """Resolve the environment-frequency efficiency-correction configuration."""
    raw = config.get("environment_frequency_efficiency_correction", False)
    if config.get("station_name") == "MINGO00":
        requested = (
            raw is not False
            and (not isinstance(raw, dict) or bool(raw.get("enabled", True)))
        )
        if requested:
            print(
                "Skipping environment-frequency efficiency correction for "
                "MINGO00: simulated data have no T/P/RH channels."
            )
        return None
    if raw is False:
        return None
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError(
            "environment_frequency_efficiency_correction must be a mapping or false"
        )
    if not bool(raw.get("enabled", True)):
        return None
    smoothing_sigma = float(raw.get("spectrum_smoothing_sigma_bins", 6.0))
    if not np.isfinite(smoothing_sigma) or smoothing_sigma <= 0:
        raise ValueError("spectrum_smoothing_sigma_bins must be positive")
    response_exponent = float(raw.get("filter_response_exponent", 0.5))
    if not np.isfinite(response_exponent) or response_exponent <= 0:
        raise ValueError("filter_response_exponent must be positive")
    response_floor = float(raw.get("filter_response_floor", 0.0))
    if not np.isfinite(response_floor) or not 0 <= response_floor < 1:
        raise ValueError("filter_response_floor must be in [0, 1)")
    variables = raw.get("environment_variables", {
        "Temperature": "sensors_ext_Temperature_ext",
        "Pressure": "sensors_ext_Pressure_ext",
        "Relative humidity": "sensors_ext_RH_ext",
    })
    if not isinstance(variables, dict) or not variables:
        raise ValueError("environment_variables must be a non-empty label: column mapping")
    return {
        "smoothing_sigma_bins": smoothing_sigma,
        "response_exponent": response_exponent,
        "response_floor": response_floor,
        "environment_variables": {
            str(label): str(column) for label, column in variables.items()
        },
        **efficiency_product_setting(config),
    }


def _regular_fourier_spectrum(
    values: pd.Series,
    sample_seconds: float,
    smoothing_sigma_bins: float,
) -> tuple[pd.DataFrame, np.ndarray, np.ndarray, np.ndarray]:
    """Return raw and Gaussian-smoothed one-sided Fourier power spectra."""
    numeric = pd.to_numeric(values, errors="coerce").astype(float)
    filled = numeric.interpolate(limit_direction="both")
    if len(filled) < 4 or not bool(np.isfinite(filled).any()):
        empty = np.full(len(values) // 2 + 1, np.nan)
        return pd.DataFrame(), np.full(len(values), np.nan), empty, empty
    filled = filled.fillna(float(filled.mean())).to_numpy(dtype=float)
    sample_index = np.arange(len(filled), dtype=float)
    slope, intercept = np.polyfit(sample_index, filled, 1)
    detrended = filled - (slope * sample_index + intercept)
    transform = np.fft.rfft(detrended)
    frequencies = np.fft.rfftfreq(len(detrended), d=sample_seconds)
    power = np.abs(transform) ** 2 / max(len(detrended), 1)
    smoothed_power = gaussian_filter1d(
        power, sigma=smoothing_sigma_bins, mode="nearest",
    )
    valid = frequencies > 0
    periods = np.divide(
        1.0, frequencies,
        out=np.full(len(frequencies), np.inf), where=frequencies > 0,
    )
    if not bool(valid.any()):
        return pd.DataFrame(), filled, frequencies, np.full(len(frequencies), np.nan)
    maximum_power = float(np.max(power[valid]))
    maximum_smoothed_power = float(np.max(smoothed_power[valid]))
    normalized_power = (
        power / maximum_power if maximum_power > 0 else np.zeros_like(power)
    )
    smoothed_normalized_power = (
        smoothed_power / maximum_smoothed_power
        if maximum_smoothed_power > 0 else np.zeros_like(smoothed_power)
    )
    smoothed_normalized_power[0] = 1.0
    spectrum = pd.DataFrame({
        "frequency_hz": frequencies[valid],
        "period_hours": periods[valid] / 3600.0,
        "power": power[valid],
        "normalized_power": normalized_power[valid],
        "smoothed_power": smoothed_power[valid],
        "smoothed_normalized_power": smoothed_normalized_power[valid],
    }).sort_values("frequency_hz").reset_index(drop=True)
    return spectrum, filled, frequencies, smoothed_normalized_power


def _environment_spectral_filter(
    values: pd.Series,
    spectral_gain: np.ndarray,
) -> np.ndarray:
    """Apply the continuous environmental gain to an efficiency Fourier series."""
    numeric = pd.to_numeric(values, errors="coerce").astype(float)
    filled = numeric.interpolate(limit_direction="both")
    if not bool(np.isfinite(filled).any()):
        return np.full(len(values), np.nan)
    filled = filled.fillna(float(filled.mean())).to_numpy(dtype=float)
    sample_index = np.arange(len(filled), dtype=float)
    slope, intercept = np.polyfit(sample_index, filled, 1)
    trend = slope * sample_index + intercept
    transform = np.fft.rfft(filled - trend)
    if len(transform) != len(spectral_gain):
        raise ValueError("Environmental spectral gain and efficiency FFT differ in size")
    transform *= spectral_gain
    filtered = trend + np.fft.irfft(transform, n=len(filled))
    return np.clip(filtered, 0.0, 1.0)


def write_environment_frequency_efficiency_correction(
    comparison_path: Path,
    environment_data_path: Path,
    setting: dict[str, Any],
    output_dir: Path,
    title: str,
    window: pd.Timedelta,
) -> tuple[list[Path], list[Path], int]:
    """Filter plane efficiencies with a continuous smooth T/P/RH spectrum."""
    output_dir.mkdir(parents=True, exist_ok=True)
    comparison = pd.read_csv(
        comparison_path, dtype={"gate_code": str}, low_memory=False,
    )
    comparison["window_start"] = pd.to_datetime(
        comparison["window_start"], errors="coerce",
    )
    comparison = comparison.dropna(subset=["window_start"])
    environment = pd.read_csv(environment_data_path, low_memory=False)
    if "Time" not in environment:
        raise ValueError("Environment data has no Time column for Fourier correction")
    environment["Time"] = pd.to_datetime(environment["Time"], errors="coerce")
    start = comparison["window_start"].min()
    end = comparison["window_start"].max()
    grid = pd.date_range(start, end, freq=window, name="window_start")
    sample_seconds = window.total_seconds()
    environment["window_start"] = environment["Time"].dt.floor(window)

    environment_spectra: list[pd.DataFrame] = []
    environment_responses: list[np.ndarray] = []
    environment_series: dict[str, pd.Series] = {}
    spectral_frequencies: np.ndarray | None = None
    for label, column in setting["environment_variables"].items():
        if column not in environment:
            raise ValueError(f"Environment Fourier column is absent: {column}")
        values = pd.to_numeric(environment[column], errors="coerce")
        by_window = values.groupby(environment["window_start"]).mean().reindex(grid)
        environment_series[label] = by_window
        spectrum, _, frequencies, smoothed_response = _regular_fourier_spectrum(
            by_window, sample_seconds, setting["smoothing_sigma_bins"],
        )
        if spectrum.empty:
            continue
        if spectral_frequencies is None:
            spectral_frequencies = frequencies
        elif not np.array_equal(spectral_frequencies, frequencies):
            raise ValueError("T/P/RH Fourier frequency grids do not match")
        spectrum.insert(0, "environment_column", column)
        spectrum.insert(0, "environment_variable", label)
        environment_spectra.append(spectrum)
        environment_responses.append(smoothed_response)
    if not environment_responses or spectral_frequencies is None:
        raise ValueError("No smooth T/P/RH Fourier response could be calculated")
    environment_spectrum = pd.concat(environment_spectra, ignore_index=True)
    combined_response = np.mean(np.vstack(environment_responses), axis=0)
    positive_response = combined_response[1:]
    response_maximum = float(np.nanmax(positive_response))
    if not np.isfinite(response_maximum) or response_maximum <= 0:
        raise ValueError("Combined smooth T/P/RH Fourier response is empty")
    combined_response = np.clip(combined_response / response_maximum, 0.0, 1.0)
    combined_response[0] = 1.0
    spectral_gain = setting["response_floor"] + (
        1.0 - setting["response_floor"]
    ) * np.power(combined_response, setting["response_exponent"])
    spectral_gain[0] = 1.0
    positive_frequency = spectral_frequencies > 0
    filter_response = pd.DataFrame({
        "frequency_hz": spectral_frequencies[positive_frequency],
        "period_hours": (
            1.0 / spectral_frequencies[positive_frequency] / 3600.0
        ),
        "combined_smoothed_environment_power_response": (
            combined_response[positive_frequency]
        ),
        "efficiency_fourier_amplitude_gain": spectral_gain[positive_frequency],
        "smoothing_sigma_bins": setting["smoothing_sigma_bins"],
        "response_exponent": setting["response_exponent"],
        "response_floor": setting["response_floor"],
    })
    environment_spectrum_path = output_dir / "environment_fourier_spectrum.csv"
    filter_response_path = output_dir / "environment_spectral_filter.csv"
    environment_spectrum.to_csv(environment_spectrum_path, index=False)
    filter_response.to_csv(filter_response_path, index=False)

    environment_plot_path = output_dir / "environment_t_p_rh_fourier_analysis.png"
    figure, axes = plt.subplots(
        len(environment_series) + 1, 1,
        figsize=(16, 4.1 * (len(environment_series) + 1)), constrained_layout=True,
        squeeze=False,
    )
    for axis, (label, _) in zip(
        axes[:-1, 0], environment_series.items(), strict=True,
    ):
        spectrum = environment_spectrum.loc[
            environment_spectrum["environment_variable"].eq(label)
        ].sort_values("period_hours")
        axis.plot(
            spectrum["period_hours"], spectrum["normalized_power"],
            color="0.55", linewidth=0.7, alpha=0.50, label="raw normalized power",
        )
        axis.plot(
            spectrum["period_hours"], spectrum["smoothed_normalized_power"],
            color="tab:blue", linewidth=2.0, label="Gaussian-smoothed power",
        )
        axis.set(
            xscale="log", xlabel="Period [hours]", ylabel="Normalized Fourier power",
            title=f"{label} Fourier spectrum",
        )
        axis.grid(True, alpha=0.25, which="both")
        axis.legend(fontsize=8)
    response_axis = axes[-1, 0]
    response_axis.plot(
        filter_response["period_hours"],
        filter_response["combined_smoothed_environment_power_response"],
        color="tab:purple", linewidth=2.0, label="combined smooth T/P/RH power",
    )
    response_axis.plot(
        filter_response["period_hours"],
        filter_response["efficiency_fourier_amplitude_gain"],
        color="tab:green", linewidth=2.0, label="applied efficiency FFT gain",
    )
    response_axis.set(
        xscale="log", xlabel="Period [hours]", ylabel="Response [0–1]",
        ylim=(-0.02, 1.02), title="Continuous environmental spectral filter",
    )
    response_axis.grid(True, alpha=0.25, which="both")
    response_axis.legend(fontsize=8)
    figure.suptitle(
        f"{title}\nSmooth environmental Fourier analysis → continuous "
        "efficiency spectral filter (no discrete period selection)",
        fontsize=14,
    )
    figure.savefig(environment_plot_path, dpi=160)
    plt.close(figure)

    efficiency_spectra: list[pd.DataFrame] = []
    correction_rows: list[pd.DataFrame] = []
    gate_plot_paths: list[Path] = []
    colors = plt.get_cmap("tab10").colors
    for gate_index, gate_code in enumerate(comparison["gate_code"].drop_duplicates()):
        gate_data = comparison.loc[
            comparison["gate_code"].eq(gate_code)
        ].set_index("window_start").reindex(grid)
        gate_label_values = gate_data["gate_label"].dropna()
        gate_label = (
            str(gate_label_values.iloc[0]) if len(gate_label_values) else str(gate_code)
        )
        filtered_columns: dict[int, np.ndarray] = {}
        raw_efficiencies: dict[int, pd.Series] = {}
        for plane in range(1, 5):
            column = f"plane_{plane}_efficiency"
            raw = pd.to_numeric(gate_data[column], errors="coerce")
            raw_efficiencies[plane] = raw
            raw_spectrum, _, _, _ = _regular_fourier_spectrum(
                raw, sample_seconds, setting["smoothing_sigma_bins"],
            )
            filtered_columns[plane] = _environment_spectral_filter(
                raw, spectral_gain,
            )
            filtered_spectrum, _, _, _ = _regular_fourier_spectrum(
                pd.Series(filtered_columns[plane], index=grid),
                sample_seconds, setting["smoothing_sigma_bins"],
            )
            if not raw_spectrum.empty and not filtered_spectrum.empty:
                spectrum = raw_spectrum.rename(columns={
                    "power": "raw_power",
                    "normalized_power": "raw_normalized_power",
                    "smoothed_power": "raw_smoothed_power",
                    "smoothed_normalized_power": "raw_smoothed_normalized_power",
                })
                spectrum["filtered_power"] = filtered_spectrum["power"]
                spectrum["filtered_normalized_power"] = filtered_spectrum[
                    "normalized_power"
                ]
                spectrum["filtered_smoothed_power"] = filtered_spectrum[
                    "smoothed_power"
                ]
                raw_smoothed_maximum = float(spectrum["raw_smoothed_power"].max())
                spectrum["filtered_smoothed_power_relative_to_raw"] = (
                    spectrum["filtered_smoothed_power"] / raw_smoothed_maximum
                    if raw_smoothed_maximum > 0 else 0.0
                )
                spectrum["environment_fourier_amplitude_gain"] = spectral_gain[1:]
                spectrum.insert(0, "plane", plane)
                spectrum.insert(0, "gate_label", gate_label)
                spectrum.insert(0, "gate_code", gate_code)
                efficiency_spectra.append(spectrum)
        filtered_frame = pd.DataFrame(
            {
                f"plane_{plane}_efficiency_filtered": filtered_columns[plane]
                for plane in range(1, 5)
            },
            index=grid,
        )
        product_planes = setting.get("efficiency_product_planes", (1, 2, 3, 4))
        filtered_product = efficiency_product_from_frame(
            filtered_frame, product_planes,
            column_template="plane_{plane}_efficiency_filtered",
        )
        inverse_product = np.divide(
            1.0, filtered_product.to_numpy(dtype=float),
            out=np.full(len(filtered_product), np.nan),
            where=np.isfinite(filtered_product.to_numpy(dtype=float))
            & (filtered_product.to_numpy(dtype=float) > 0),
        )
        raw_1234_rate = pd.to_numeric(
            gate_data["topology_1234_rate_hz"], errors="coerce",
        )
        corrected_rate = raw_1234_rate.to_numpy(dtype=float) * inverse_product
        raw_rate_values = raw_1234_rate.to_numpy(dtype=float)
        raw_rate_reference = float(np.nanmean(raw_rate_values))
        corrected_rate_reference = float(np.nanmean(corrected_rate))
        relative_raw_rate = np.divide(
            raw_rate_values, raw_rate_reference,
            out=np.full(len(raw_rate_values), np.nan),
            where=np.isfinite(raw_rate_values) & np.isfinite(raw_rate_reference)
            & (raw_rate_reference > 0),
        )
        relative_corrected_rate = np.divide(
            corrected_rate, corrected_rate_reference,
            out=np.full(len(corrected_rate), np.nan),
            where=np.isfinite(corrected_rate) & np.isfinite(corrected_rate_reference)
            & (corrected_rate_reference > 0),
        )
        correction = pd.DataFrame({
            "window_start": grid,
            "gate_code": gate_code,
            "gate_label": gate_label,
            **{
                f"plane_{plane}_efficiency_raw": raw_efficiencies[plane].to_numpy()
                for plane in range(1, 5)
            },
            **{
                f"plane_{plane}_efficiency_filtered": filtered_columns[plane]
                for plane in range(1, 5)
            },
            "filtered_efficiency_product": filtered_product.to_numpy(),
            "efficiency_product_mode": setting.get("efficiency_product_mode", "all_planes"),
            "efficiency_product_plane_numbers": ",".join(
                str(plane) for plane in product_planes
            ),
            "inverse_filtered_efficiency_product": inverse_product,
            "topology_1234_rate_hz": raw_rate_values,
            "environment_frequency_corrected_1234_rate_hz": corrected_rate,
            "topology_1234_rate_reference_hz": raw_rate_reference,
            "relative_topology_1234_rate": relative_raw_rate,
            "environment_frequency_corrected_1234_rate_reference_hz": (
                corrected_rate_reference
            ),
            "relative_environment_frequency_corrected_1234_rate": (
                relative_corrected_rate
            ),
            "spectral_smoothing_sigma_bins": setting["smoothing_sigma_bins"],
            "spectral_filter_response_exponent": setting["response_exponent"],
            "spectral_filter_response_floor": setting["response_floor"],
        })
        correction_rows.append(correction)

        gate_plot_path = output_dir / (
            f"gate_{gate_code}_environment_frequency_efficiency_correction.png"
        )
        gate_figure, gate_axes = plt.subplots(
            5, 1, figsize=(18, 21), constrained_layout=True,
        )
        gate_spectra = [
            spectrum for spectrum in efficiency_spectra
            if str(spectrum["gate_code"].iloc[0]) == str(gate_code)
        ]
        for spectrum in gate_spectra:
            plane = int(spectrum["plane"].iloc[0])
            gate_axes[0].plot(
                spectrum["period_hours"],
                spectrum["raw_smoothed_normalized_power"],
                color=colors[(plane - 1) % len(colors)], linewidth=0.9,
                linestyle="--", alpha=0.48, label=f"Plane {plane} raw smooth",
            )
            gate_axes[0].plot(
                spectrum["period_hours"],
                spectrum["filtered_smoothed_power_relative_to_raw"],
                color=colors[(plane - 1) % len(colors)], linewidth=1.7,
                label=f"Plane {plane} filtered smooth",
            )
        gate_axes[0].plot(
            filter_response["period_hours"],
            filter_response["efficiency_fourier_amplitude_gain"],
            color="black", linewidth=2.0, alpha=0.72,
            label="continuous environmental FFT gain",
        )
        gate_axes[0].set(
            xscale="log", xlabel="Period [hours]", ylabel="Relative spectral response",
            ylim=(-0.02, 1.05),
            title=(
                "Smooth efficiency spectra before and after filtering | product: "
                + setting["efficiency_product_label"]
            ),
        )
        for plane in range(1, 5):
            color = colors[(plane - 1) % len(colors)]
            gate_axes[1].scatter(
                grid, raw_efficiencies[plane], s=8, alpha=0.25, color=color,
                edgecolors="none", rasterized=True,
            )
            gate_axes[1].plot(
                grid, filtered_columns[plane], color=color, linewidth=1.25,
                label=f"Plane {plane} filtered",
            )
        gate_axes[1].set(
            ylabel="Plane efficiency", ylim=(-0.02, 1.02),
            title="Raw points and continuous environment-spectrum filtered efficiencies",
        )
        product_axis = gate_axes[2]
        inverse_axis = product_axis.twinx()
        product_axis.plot(
            grid, filtered_product, color="tab:blue", linewidth=1.3,
            label="Filtered efficiency product",
        )
        inverse_axis.plot(
            grid, inverse_product, color="tab:orange", linewidth=1.1,
            label="1 / filtered efficiency product",
        )
        product_axis.set(ylabel="Filtered efficiency product", title="Product and inverse product")
        inverse_axis.set_ylabel("Inverse filtered efficiency product")
        product_axis.legend(loc="upper left", fontsize=8)
        inverse_axis.legend(loc="upper right", fontsize=8)
        gate_axes[3].scatter(
            grid, raw_1234_rate, s=10, color="0.35", alpha=0.42,
            edgecolors="none", label="Raw 1234 rate", rasterized=True,
        )
        gate_axes[3].scatter(
            grid, corrected_rate, s=10, color="tab:green", alpha=0.62,
            edgecolors="none", label="1234 rate / filtered efficiency product",
            rasterized=True,
        )
        gate_axes[3].set(
            ylabel="Rate [Hz]",
            title="Environment-frequency efficiency correction",
        )
        gate_axes[4].scatter(
            grid, relative_raw_rate, s=10, color="0.35", alpha=0.42,
            edgecolors="none", label="Relative raw 1234 rate", rasterized=True,
        )
        gate_axes[4].scatter(
            grid, relative_corrected_rate, s=10, color="tab:green", alpha=0.62,
            edgecolors="none", label="Relative corrected 1234 rate", rasterized=True,
        )
        gate_axes[4].axhline(
            1.0, color="0.25", linewidth=1.0, linestyle="--",
        )
        gate_axes[4].set(
            xlabel="Time", ylabel="Relative rate",
            title="Raw and corrected rates normalized by their respective means",
        )
        for axis in gate_axes:
            axis.grid(True, alpha=0.25)
        gate_axes[0].legend(fontsize=8, ncols=3)
        gate_axes[1].legend(fontsize=8, ncols=4)
        gate_axes[3].legend(fontsize=8)
        gate_axes[4].legend(fontsize=8)
        gate_figure.suptitle(
            f"{title}\nGate {gate_label} [{gate_code}] | smooth T/P/RH spectrum → "
            "filtered plane efficiencies → product → corrected 1234 rate",
            fontsize=14,
        )
        gate_figure.autofmt_xdate()
        gate_figure.savefig(gate_plot_path, dpi=160)
        plt.close(gate_figure)
        gate_plot_paths.append(gate_plot_path)

    efficiency_spectrum = pd.concat(efficiency_spectra, ignore_index=True)
    corrections = pd.concat(correction_rows, ignore_index=True)
    efficiency_spectrum_path = output_dir / "plane_efficiency_fourier_spectrum.csv"
    corrections_path = output_dir / "filtered_efficiency_correction.csv"
    efficiency_spectrum.to_csv(efficiency_spectrum_path, index=False)
    corrections.to_csv(corrections_path, index=False)
    csv_paths = [
        environment_spectrum_path, filter_response_path,
        efficiency_spectrum_path, corrections_path,
    ]
    plot_paths = [environment_plot_path, *gate_plot_paths]
    print(
        f"Environment-frequency efficiency correction: {len(gate_plot_paths)} gate(s), "
        f"continuous spectral filter with sigma={setting['smoothing_sigma_bins']:g} bins"
    )
    return plot_paths, csv_paths, len(plot_paths)



def plane_combination_setting(
    config: dict[str, Any], gates: list[Gate], available: set[str],
) -> dict[str, Any] | None:
    raw = config.get("plane_combinations", {})
    if raw is False:
        return None
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("plane_combinations must be a YAML mapping or false")
    if not bool(raw.get("enabled", True)):
        return None
    time_column = str(raw.get("time_column", "datetime")).strip()
    topology_column = str(raw.get("topology_column", "tt_task3_list")).strip()
    missing = sorted({time_column, topology_column} - available)
    if missing:
        raise ValueError("Plane-combination columns absent from schema: " + ", ".join(missing))
    try:
        window = pd.Timedelta(str(raw.get("accumulation_timespan", "10min")))
    except ValueError as exc:
        raise ValueError("Invalid plane_combinations.accumulation_timespan") from exc
    if window <= pd.Timedelta(0):
        raise ValueError("plane_combinations.accumulation_timespan must be positive")
    kind = str(raw.get("selection_kind", "individual")).strip().lower()
    kind = {"combined": "combined_exact", "exact": "combined_exact"}.get(kind, kind)
    if kind not in {"individual", "combined_exact"}:
        raise ValueError("plane_combinations.selection_kind must be individual or combined_exact")
    if kind == "individual":
        gate = gate_from_short_label(
            gates, raw.get("gate_label", gates[-1].short_label),
            location="plane_combinations.gate_label",
        )
        code = gate.code
    else:
        code = combined_decimal_code_from_labels(
            gates, raw.get("gate_labels"),
            location="plane_combinations.gate_labels",
        )
    return {
        "time_column": time_column,
        "topology_column": topology_column,
        "window": window,
        "kind": kind,
        "code": code,
        **efficiency_product_setting(config),
    }


def write_plane_combination_timeseries(
    frame: pd.DataFrame,
    gates: list[Gate],
    masks: dict[str, pd.Series],
    setting: dict[str, Any],
    output_dir: Path,
    title: str,
) -> tuple[Path, Path, int]:
    kind = setting["kind"]
    code = setting["code"]
    window = setting["window"]
    time_column = setting["time_column"]
    topology_column = setting["topology_column"]
    if kind == "individual":
        gate = next(gate for gate in gates if gate.code == code)
        selection_name = gate.name
        gate_mask = masks[code]
    else:
        selection_name = combined_name(code, gates)
        gate_mask = frame["gate_code"].astype(str).eq(code)

    timestamps = pd.to_datetime(frame[time_column], errors="coerce")
    topology_numeric = pd.to_numeric(frame[topology_column], errors="coerce")
    topologies = topology_numeric.where(topology_numeric.mod(1).eq(0)).astype("Int64").astype("string")
    valid_time = timestamps.notna()
    if not bool(valid_time.any()):
        raise ValueError(f"{time_column} contains no valid timestamps")
    seconds = timestamps.loc[valid_time].dt.floor("s")
    all_windows = pd.DatetimeIndex(
        timestamps.loc[valid_time].dt.floor(window).drop_duplicates().sort_values(),
        name="window_start",
    )
    exposure = pd.DataFrame({
        "window_start": seconds.dt.floor(window),
        "second": seconds,
    }).groupby("window_start")["second"].nunique().reindex(all_windows, fill_value=0)

    selected = valid_time & gate_mask
    selected_events = pd.DataFrame({
        "window_start": timestamps.loc[selected].dt.floor(window),
        "topology": topologies.loc[selected],
    })
    counts = selected_events.groupby(["window_start", "topology"]).size().unstack(fill_value=0)
    counts = counts.reindex(all_windows, fill_value=0)
    counted_topologies = ("123", "124", "134", "234", "1234")
    for topology in counted_topologies:
        if topology not in counts:
            counts[topology] = 0

    summary = pd.DataFrame({
        "window_start": all_windows,
        "window_end": all_windows + window,
        "selection_kind": kind,
        "gate_code": code,
        "gate_name": selection_name,
        "observed_seconds": exposure.to_numpy(dtype=np.int64),
    })
    for topology in counted_topologies:
        summary[f"topology_{topology}_count"] = (
            pd.to_numeric(counts[topology], errors="coerce").fillna(0).astype(np.int64).to_numpy()
        )
    detected = summary["topology_1234_count"].to_numpy(dtype=float)
    missing_topology = {1: "234", 2: "134", 3: "124", 4: "123"}
    for plane, missing_code in missing_topology.items():
        undetected = summary[f"topology_{missing_code}_count"].to_numpy(dtype=float)
        denominator = detected + undetected
        summary[f"plane_{plane}_efficiency"] = np.divide(
            detected, denominator,
            out=np.full(len(denominator), np.nan), where=denominator > 0,
        )
    product_planes = setting.get("efficiency_product_planes", (1, 2, 3, 4))
    summary["efficiency_product"] = efficiency_product_from_frame(
        summary, product_planes, column_template="plane_{plane}_efficiency",
    )
    summary["efficiency_product_mode"] = setting.get("efficiency_product_mode", "all_planes")
    summary["efficiency_product_plane_numbers"] = ",".join(
        str(plane) for plane in product_planes
    )
    observed_seconds = summary["observed_seconds"].to_numpy(dtype=float)
    summary["topology_1234_rate_hz"] = np.divide(
        detected, observed_seconds,
        out=np.full(len(observed_seconds), np.nan), where=observed_seconds > 0,
    )
    efficiency_product = summary["efficiency_product"].to_numpy(dtype=float)
    raw_rate = summary["topology_1234_rate_hz"].to_numpy(dtype=float)
    summary["efficiency_corrected_rate_hz"] = np.divide(
        raw_rate, efficiency_product,
        out=np.full(len(raw_rate), np.nan),
        where=np.isfinite(efficiency_product) & (efficiency_product > 0),
    )

    csv_path = output_dir / f"plane_combinations_{kind}_{code}.csv"
    summary.to_csv(csv_path, index=False)
    fig, axes = plt.subplots(3, 1, figsize=(16, 12), sharex=True, constrained_layout=True)
    axes[0].plot(
        summary["window_start"], summary["topology_1234_rate_hz"],
        color="tab:blue", marker=".", markersize=4, linewidth=1.2,
    )
    axes[0].set_ylabel("1234 rate [Hz]")
    axes[0].set_title("Observed four-plane (1234) event rate")
    for plane in range(1, 5):
        axes[1].plot(
            summary["window_start"], summary[f"plane_{plane}_efficiency"],
            marker=".", markersize=3, linewidth=1.0, label=f"Plane {plane}",
        )
    axes[1].plot(
        summary["window_start"], summary["efficiency_product"],
        color="black", linestyle="--", linewidth=1.8, label="efficiency product",
    )
    axes[1].set(ylabel="Efficiency", ylim=(-0.02, 1.02),
                title=(
                    "Plane efficiencies and product of "
                    + setting["efficiency_product_label"]
                ))
    axes[1].legend(ncols=5)
    axes[2].plot(
        summary["window_start"], summary["efficiency_corrected_rate_hz"],
        color="tab:red", marker=".", markersize=4, linewidth=1.2,
    )
    axes[2].set(
        xlabel="Time", ylabel="Corrected rate [Hz]",
        title="1234 rate / efficiency product",
    )
    for axis in axes:
        axis.grid(True, alpha=0.25)
    fig.suptitle(
        f"{title}" + chr(10) + f"{kind} gate {code}: {selection_name} | accumulation={window} | "
        "rate denominator=observed timestamp-seconds",
        fontsize=14,
    )
    fig.autofmt_xdate()
    plot_path = output_dir / f"plane_combinations_{kind}_{code}.png"
    fig.savefig(plot_path, dpi=160)
    plt.close(fig)
    print(
        f"Plane combinations: {kind} gate {code}, {len(summary)} window(s), "
        f"accumulation={window}"
    )
    return plot_path, csv_path, 1


def angular_histogram_setting(
    config: dict[str, Any], available: set[str],
) -> dict[str, Any] | None:
    raw = config.get("angular_histograms", config.get("theta_histograms", {}))
    if raw is False:
        return None
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("angular_histograms must be a YAML mapping or false")
    if not bool(raw.get("enabled", True)):
        return None
    raw_variables = raw.get("variables")
    if raw_variables is None:
        raw_variables = [{
            "column": str(raw.get("column", "event_theta")),
            "label": "Theta",
            "slug": "theta",
            "bins": raw.get("bins", 90),
            "range": raw.get("range", [0, 90]),
        }]
    if not isinstance(raw_variables, list) or not raw_variables:
        raise ValueError("angular_histograms.variables must be a nonempty list")
    variables: list[dict[str, Any]] = []
    seen_slugs: set[str] = set()
    for index, item in enumerate(raw_variables, 1):
        if not isinstance(item, dict):
            raise ValueError(f"angular_histograms.variables item {index} must be a mapping")
        column = str(item.get("column", "")).strip()
        label = str(item.get("label", column)).strip()
        slug = str(item.get("slug", label)).strip().lower()
        slug = re.sub(r"[^a-z0-9]+", "_", slug).strip("_")
        if not column or not label or not slug:
            raise ValueError(f"angular_histograms.variables item {index} needs column and label")
        if column not in available:
            raise ValueError(f"Angular histogram column absent from schema: {column}")
        sign_column = str(item.get("sign_by_cosine_column", "")).strip()
        if sign_column and sign_column not in available:
            raise ValueError(
                f"Angular histogram sign column absent from schema: {sign_column}"
            )
        if slug in seen_slugs:
            raise ValueError(f"Duplicate angular histogram slug: {slug}")
        bins = int(item.get("bins", raw.get("bins", 90)))
        if bins < 1:
            raise ValueError(f"angular_histograms variable {slug} bins must be positive")
        value_range = item.get("range", raw.get("range", [0, 90]))
        if not isinstance(value_range, (list, tuple)) or len(value_range) != 2:
            raise ValueError(f"angular_histograms variable {slug} range needs [min, max]")
        lower, upper = float(value_range[0]), float(value_range[1])
        if lower >= upper:
            raise ValueError(f"angular_histograms variable {slug} range must be increasing")
        variables.append({
            "column": column,
            "label": label,
            "slug": slug,
            "bins": bins,
            "range": (lower, upper),
            "sign_by_cosine_column": sign_column or None,
        })
        seen_slugs.add(slug)
    z_columns = [f"z_p{plane}" for plane in range(1, 5)]
    if not set(z_columns).issubset(available):
        z_columns = []
    raw_asymmetry = raw.get("phi_asymmetry_scan", False)
    if raw_asymmetry is False:
        phi_asymmetry = None
    else:
        if raw_asymmetry is None:
            raw_asymmetry = {}
        if not isinstance(raw_asymmetry, dict):
            raise ValueError("angular_histograms.phi_asymmetry_scan must be a mapping or false")
        if not bool(raw_asymmetry.get("enabled", True)):
            phi_asymmetry = None
        else:
            variable_slug = str(raw_asymmetry.get("variable_slug", "phi")).strip().lower()
            matches = [variable for variable in variables if variable["slug"] == variable_slug]
            if not matches:
                raise ValueError(
                    "Phi asymmetry variable slug is not configured: " + variable_slug
                )
            cut_step = float(raw_asymmetry.get("cut_step", 1.0))
            if not np.isfinite(cut_step) or cut_step <= 0 or cut_step > 180:
                raise ValueError("Phi asymmetry cut_step must be in (0, 180]")
            percentage_limit = float(raw_asymmetry.get("percentage_limit", 50.0))
            if not np.isfinite(percentage_limit) or percentage_limit <= 0:
                raise ValueError(
                    "Phi asymmetry percentage_limit must be a positive number"
                )
            phi_asymmetry = {
                "variable": matches[0],
                "cut_step": cut_step,
                "plot_percentage": bool(raw_asymmetry.get("plot_percentage", True)),
                "percentage_limit": percentage_limit,
            }
    return {
        "variables": variables,
        "degrees": bool(raw.get("convert_radians_to_degrees", True)),
        "include_combined_exact": bool(raw.get("include_combined_exact", True)),
        "include_combined_zero": bool(raw.get("include_combined_zero", True)),
        "z_columns": z_columns,
        "z_unit": str(raw.get("plane_z_unit", "mm")).strip(),
        "phi_asymmetry": phi_asymmetry,
    }


def charge_calibration_comparison_setting(
    config: dict[str, Any], available: set[str],
) -> dict[str, Any] | None:
    """Resolve the non-commuting strip-sum/calibration comparison."""
    raw = config.get("charge_calibration_comparison", {})
    if raw is False:
        return None
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("charge_calibration_comparison must be a YAML mapping or false")
    if not bool(raw.get("enabled", True)):
        return None
    suffix = str(raw.get("source_suffix", "qsum_cal")).strip()
    columns = [
        f"p{plane}_s{strip}_{suffix}"
        for plane in range(1, 5)
        for strip in range(1, 5)
    ]
    missing = sorted(set(columns) - available)
    if missing:
        raise ValueError(
            "Charge-calibration comparison columns absent from schema: "
            + ", ".join(missing)
        )
    raw_bins = raw.get("bins", 100)
    if isinstance(raw_bins, str) and raw_bins.strip().lower() == "auto":
        bins: int | str = "auto"
    else:
        bins = int(raw_bins)
        if bins < 1:
            raise ValueError(
                "charge_calibration_comparison.bins must be a positive integer or auto"
            )
    minimum_active = int(raw.get("min_active_strips", 2))
    if not 1 <= minimum_active <= 4:
        raise ValueError(
            "charge_calibration_comparison.min_active_strips must be in 1..4"
        )
    return {
        "suffix": suffix,
        "columns": columns,
        "bins": bins,
        "minimum_active": minimum_active,
    }


def write_per_strip_charge_histograms(
    frame: pd.DataFrame,
    setting: dict[str, Any],
    spline: CubicSpline,
    width_domain: tuple[float, float],
    output_dir: Path,
    title: str,
) -> tuple[Path, Path]:
    """Write matching 4x4 strip-ToT and calibrated-charge histogram grids."""
    source_labels = (
        frame["_source_basename"].astype(str).to_numpy()
        if "_source_basename" in frame.columns
        else np.full(len(frame), "selected data", dtype=object)
    )
    source_order = list(dict.fromkeys(source_labels.tolist()))
    source_colors = plt.get_cmap("tab10").colors
    suffix = setting["suffix"]
    specifications = [
        (
            "00_per_strip_uncalibrated_tot_histograms.png",
            "Uncalibrated ToT input within calibration domain", "ToT (ns)", False,
        ),
        (
            "01_per_strip_calibrated_charge_histograms.png",
            "ToT-to-charge calibrated", "Charge (fC)", True,
        ),
    ]
    written: list[Path] = []
    for filename, diagnostic_label, x_label, apply_spline in specifications:
        figure, axes = plt.subplots(
            4, 4, figsize=(16, 12), constrained_layout=True,
        )
        legend_handles: list[Any] = []
        legend_labels: list[str] = []
        for plane in range(1, 5):
            for strip in range(1, 5):
                axis = axes[plane - 1, strip - 1]
                column = f"p{plane}_s{strip}_{suffix}"
                widths = pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype=float)
                positive = np.isfinite(widths) & (widths > 0)
                in_domain = (widths >= width_domain[0]) & (widths <= width_domain[1])
                out_of_domain_count = int((positive & ~in_domain).sum())
                valid = positive & in_domain
                parts: list[np.ndarray] = []
                part_labels: list[str] = []
                part_colors: list[Any] = []
                for source_index, source_name in enumerate(source_order):
                    source_mask = valid & (source_labels == source_name)
                    if not np.any(source_mask):
                        continue
                    values = widths[source_mask]
                    parts.append(spline(values) if apply_spline else values)
                    part_labels.append(source_name)
                    part_colors.append(source_colors[source_index % len(source_colors)])
                if parts:
                    edges = np.histogram_bin_edges(
                        np.concatenate(parts), bins=setting["bins"],
                    )
                    for values, part_label, part_color in zip(
                        parts, part_labels, part_colors, strict=True,
                    ):
                        axis.hist(
                            values, bins=edges, histtype="step", linewidth=1.25,
                            color=part_color, label=part_label,
                        )
                    if not legend_handles:
                        legend_handles, legend_labels = axis.get_legend_handles_labels()
                else:
                    axis.text(
                        0.5, 0.5, "No positive values", ha="center", va="center",
                        transform=axis.transAxes,
                    )
                axis.set_title(
                    f"Plane {plane}, strip {strip} "
                    f"(N={sum(len(part) for part in parts):,}, out={out_of_domain_count:,})",
                    fontsize=10,
                )
                axis.grid(True, alpha=0.22)
        figure.supxlabel(x_label)
        figure.supylabel("Count")
        figure.suptitle(
            f"{title.partition("|")[0].strip()} | {diagnostic_label} per strip\n"
            f"source: p#_s#_{suffix}",
            fontsize=15,
        )
        if legend_handles:
            figure.legend(
                legend_handles, legend_labels, loc="upper right",
                fontsize=8, title="Source file",
            )
        destination = output_dir / filename
        figure.savefig(destination, dpi=160)
        plt.close(figure)
        written.append(destination)
        print(f"Per-strip charge diagnostic: {destination}")
    return written[0], written[1]


def write_charge_calibration_comparison(
    frame: pd.DataFrame,
    setting: dict[str, Any],
    output_dir: Path,
    title: str,
) -> tuple[Path, int]:
    """Compare sum(calibrate(strip ToT)) with calibrate(sum(strip ToT))."""
    calibration = pd.read_csv(TOT_TO_CHARGE_CALIBRATION)
    required = {"Width", "Fast_Charge"}
    if not required.issubset(calibration.columns):
        raise ValueError(
            f"Expected {required} in charge calibration {TOT_TO_CHARGE_CALIBRATION}"
        )
    calibration = calibration.loc[:, ["Width", "Fast_Charge"]].apply(
        pd.to_numeric, errors="coerce"
    ).dropna().sort_values("Width")
    widths_table = calibration["Width"].to_numpy(dtype=float)
    charges_table = calibration["Fast_Charge"].to_numpy(dtype=float)
    if len(widths_table) < 2 or np.any(np.diff(widths_table) <= 0):
        raise ValueError("Charge-calibration widths must be strictly increasing")
    spline = CubicSpline(widths_table, charges_table, bc_type="natural")
    write_per_strip_charge_histograms(
        frame, setting, spline, (float(widths_table[0]), float(widths_table[-1])),
        output_dir, title,
    )

    calibrate_then_sum: list[np.ndarray] = []
    sum_then_calibrate: list[np.ndarray] = []
    source_by_observation: list[np.ndarray] = []
    plane_by_observation: list[np.ndarray] = []
    source_labels = (
        frame["_source_basename"].astype(str).to_numpy()
        if "_source_basename" in frame.columns
        else np.full(len(frame), "selected data", dtype=object)
    )
    suffix = setting["suffix"]
    rejected_outside_domain = 0
    for plane in range(1, 5):
        columns = [f"p{plane}_s{strip}_{suffix}" for strip in range(1, 5)]
        widths = frame[columns].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
        active = np.isfinite(widths) & (widths > 0)
        active_count = active.sum(axis=1)
        positive_widths = np.where(active, widths, 0.0)
        width_sum = positive_widths.sum(axis=1)
        in_domain = (
            np.all(~active | (widths <= widths_table[-1]), axis=1)
            & (width_sum >= widths_table[0])
            & (width_sum <= widths_table[-1])
        )
        candidate = active_count >= setting["minimum_active"]
        valid = candidate & in_domain
        rejected_outside_domain += int((candidate & ~in_domain).sum())
        if not np.any(valid):
            continue
        strip_charges = np.where(active[valid], spline(widths[valid]), 0.0)
        calibrate_then_sum.append(strip_charges.sum(axis=1))
        sum_then_calibrate.append(spline(width_sum[valid]))
        source_by_observation.append(source_labels[valid])
        plane_by_observation.append(
            np.full(int(valid.sum()), plane, dtype=np.int8)
        )

    plot_path = output_dir / "strip_charge_calibration_order_comparison.png"
    if not calibrate_then_sum:
        raise ValueError(
            "No valid multi-strip plane events remained for the charge-calibration "
            "order comparison"
        )
    first = np.concatenate(calibrate_then_sum)
    second = np.concatenate(sum_then_calibrate)
    sources = np.concatenate(source_by_observation)
    planes = np.concatenate(plane_by_observation)
    combined = np.concatenate((first, second))
    edges = np.histogram_bin_edges(combined, bins=setting["bins"])
    difference = first - second

    fig, axes = plt.subplots(
        2, 2, figsize=(14, 10), sharex=True, sharey=True,
        constrained_layout=True,
    )
    legend_handles: list[Any] = []
    legend_labels: list[str] = []
    for plane in range(1, 5):
        axis = axes.flat[plane - 1]
        plane_mask = planes == plane
        plane_first = first[plane_mask]
        plane_second = second[plane_mask]
        axis.hist(
            plane_first, bins=edges, histtype="stepfilled", alpha=0.30,
            linewidth=1.6, color="tab:blue",
            label="sum of calibrated strip charges",
        )
        axis.hist(
            plane_second, bins=edges, histtype="step", linewidth=2.0,
            color="tab:orange", label="calibration of summed strip ToT",
        )
        axis.set_title(f"Plane {plane}")
        axis.grid(True, alpha=0.25)
        if len(plane_first):
            plane_difference = plane_first - plane_second
            annotation = (
                f"N = {len(plane_first):,}\n"
                f"median difference = {np.median(plane_difference):+.1f} fC"
            )
        else:
            annotation = "No valid plane events"
        axis.text(
            0.98, 0.97, annotation,
            transform=axis.transAxes, ha="right", va="top",
            bbox={"facecolor": "white", "alpha": 0.85, "edgecolor": "0.75"},
        )
        if not legend_handles:
            legend_handles, legend_labels = axis.get_legend_handles_labels()
    fig.supxlabel("Plane charge (fC)")
    fig.supylabel("Plane-event count")
    fig.suptitle(
        f"{title.partition("|")[0].strip()} | ToT-to-charge calibration order by plane\n"
        f"(at least {setting['minimum_active']} active strips)",
        fontsize=15,
    )
    if legend_handles:
        fig.legend(
            legend_handles, legend_labels, loc="upper right",
            bbox_to_anchor=(0.99, 0.96), fontsize=9,
        )
    fig.savefig(plot_path, dpi=160)
    plt.close(fig)

    scatter_path = output_dir / "strip_charge_calibration_order_scatter.png"
    scatter_fig, scatter_axes = plt.subplots(
        2, 2, figsize=(11, 10), sharex=True, sharey=True,
        constrained_layout=True,
    )
    source_order = list(dict.fromkeys(sources.tolist()))
    source_colors = plt.get_cmap("tab10").colors
    lower = float(combined.min())
    upper = float(combined.max())
    for plane in range(1, 5):
        scatter_axis = scatter_axes.flat[plane - 1]
        plane_mask = planes == plane
        for source_index, source_name in enumerate(source_order):
            selection = plane_mask & (sources == source_name)
            if not np.any(selection):
                continue
            scatter_axis.scatter(
                second[selection], first[selection], s=7, alpha=0.22,
                color=source_colors[source_index % len(source_colors)],
                edgecolors="none", rasterized=True, label=source_name,
            )
        scatter_axis.plot(
            [lower, upper], [lower, upper], color="black", linestyle="--",
            linewidth=1.2, label="equal charge",
        )
        plane_difference = difference[plane_mask]
        scatter_axis.set(
            xlim=(lower, upper), ylim=(lower, upper),
            title=f"Plane {plane} (N={int(plane_mask.sum()):,})",
        )
        scatter_axis.set_aspect("equal", adjustable="box")
        scatter_axis.grid(True, alpha=0.25)
        scatter_axis.text(
            0.03, 0.97,
            f"median y - x = {np.median(plane_difference):+.1f} fC",
            transform=scatter_axis.transAxes, ha="left", va="top", fontsize=9,
            bbox={"facecolor": "white", "alpha": 0.85, "edgecolor": "0.75"},
        )
    for scatter_axis in scatter_axes[1, :]:
        scatter_axis.set_xlabel("Calibration of summed strip ToT (fC)")
    for scatter_axis in scatter_axes[:, 0]:
        scatter_axis.set_ylabel("Sum of calibrated strip charges (fC)")
    scatter_axes[1, 1].legend(
        loc="lower right", fontsize=8, title="Source file / reference",
    )
    scatter_fig.suptitle(
        f"{title.partition("|")[0].strip()} | Calibration-order scatter by plane\n"
        f"(at least {setting['minimum_active']} active strips)",
        fontsize=15,
    )
    scatter_fig.savefig(scatter_path, dpi=160)
    plt.close(scatter_fig)
    print(f"Charge-calibration scatter: {scatter_path}")
    print(
        f"Charge-calibration comparison: {len(first):,} plane events; "
        f"excluded {rejected_outside_domain:,} outside the "
        f"[{widths_table[0]:g}, {widths_table[-1]:g}] ns calibration domain."
    )
    return plot_path, len(first)


def angular_values(
    frame: pd.DataFrame,
    variable: dict[str, Any],
    *,
    convert_to_degrees: bool,
) -> tuple[np.ndarray, str]:
    """Return an angle, optionally signed by the cosine of another radian angle."""
    angle = pd.to_numeric(frame[variable["column"]], errors="coerce").to_numpy(dtype=float)
    sign_column = variable.get("sign_by_cosine_column")
    if sign_column:
        direction = pd.to_numeric(frame[sign_column], errors="coerce").to_numpy(dtype=float)
        valid_direction = np.isfinite(direction)
        direction_sign = np.where(np.cos(direction) >= 0, 1.0, -1.0)
        angle = np.where(valid_direction, angle * direction_sign, np.nan)
    if convert_to_degrees:
        return np.degrees(angle), "degrees"
    return angle, "radians"


def write_angular_histogram_comparison(
    frame: pd.DataFrame,
    gates: list[Gate],
    masks: dict[str, pd.Series],
    setting: dict[str, Any],
    variable: dict[str, Any],
    output_dir: Path,
    title: str,
) -> tuple[Path, int]:
    angle_column = variable["column"]
    angle_label = variable["label"]
    angle_slug = variable["slug"]
    angle, unit = angular_values(
        frame, variable, convert_to_degrees=setting["degrees"],
    )
    finite = np.isfinite(angle)
    selections: list[tuple[str, str, str, np.ndarray]] = []
    for gate in gates:
        selections.append((
            "individual", gate.code, gate.name, masks[gate.code].to_numpy(dtype=bool),
        ))
    if setting["include_combined_exact"]:
        combined_codes = sorted(
            frame["gate_code"].dropna().astype(str).unique(),
            key=lambda code: int(code),
        )
        for code in combined_codes:
            if code == "0" and not setting["include_combined_zero"]:
                continue
            selections.append((
                "combined_exact", code, combined_name(code, gates),
                frame["gate_code"].astype(str).eq(code).to_numpy(dtype=bool),
            ))

    edges = np.linspace(variable["range"][0], variable["range"][1], variable["bins"] + 1)
    bin_widths = np.diff(edges)
    histogram_rows: list[dict[str, Any]] = []
    plot_kinds = (
        ("individual", "combined_exact")
        if setting["include_combined_exact"] else ("individual",)
    )
    fig, raw_axes = plt.subplots(
        len(plot_kinds), 1, figsize=(15, 11 if len(plot_kinds) == 2 else 6.5),
        constrained_layout=True, sharex=True,
    )
    axes = np.atleast_1d(raw_axes)
    axes_by_kind = dict(zip(plot_kinds, axes, strict=True))
    plotted_by_kind = {kind: 0 for kind in plot_kinds}

    for kind, code, name, gate_mask in selections:
        values = angle[finite & gate_mask]
        counts, _ = np.histogram(values, bins=edges)
        in_range_events = int(counts.sum())
        density = (
            counts.astype(float) / (in_range_events * bin_widths)
            if in_range_events > 0
            else np.zeros_like(bin_widths, dtype=float)
        )
        for index, count in enumerate(counts):
            histogram_rows.append({
                "kind": kind,
                "gate_code": code,
                "gate_name": name,
                "bin_left": edges[index],
                "bin_right": edges[index + 1],
                "events": int(count),
                "density": float(density[index]),
                "finite_events": int(values.size),
                "in_range_events": in_range_events,
            })
        if in_range_events == 0:
            print(f"Warning: no in-range {angle_label} values for {kind} gate {code}")
            continue
        legend_name = (
            next(gate.short_label or gate.name for gate in gates if gate.code == code)
            if kind == "individual" else combined_short_label(code, gates)
        )
        axes_by_kind[kind].stairs(
            density,
            edges,
            linewidth=1.5,
            label=f"{legend_name} (n={in_range_events:,})",
        )
        plotted_by_kind[kind] += 1

    density_unit = f"1/{unit}"
    axes[0].set(
        xlabel=f"{angle_slug} [{unit}]" if len(plot_kinds) == 1 else None,
        ylabel=f"Probability density [{density_unit}]",
        title="Individual gates (events may appear in more than one curve)",
    )
    if len(plot_kinds) == 2:
        axes[1].set(
            xlabel=f"{angle_slug} [{unit}]",
            ylabel=f"Probability density [{density_unit}]",
            title="Exact combined gate codes (mutually exclusive)",
        )
    for kind, axis in axes_by_kind.items():
        axis.grid(True, alpha=0.25)
        if plotted_by_kind[kind]:
            axis.legend(fontsize=7, ncols=2)
        else:
            axis.text(
                0.5, 0.5, "No populated gates", ha="center", va="center",
                transform=axis.transAxes,
            )
    title_parts = [part.strip() for part in title.split("|")]
    compact_title = " | ".join(title_parts[:3])
    z_labels: list[str] = []
    for plane, column in enumerate(setting["z_columns"], 1):
        values = pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype=float)
        finite_values = values[np.isfinite(values)]
        if not len(finite_values):
            label = "n/a"
        else:
            lower_z = float(np.min(finite_values))
            upper_z = float(np.max(finite_values))
            label = f"{lower_z:g}" if np.isclose(lower_z, upper_z) else f"{lower_z:g}–{upper_z:g}"
        z_labels.append(f"P{plane}={label}")
    z_title = (
        f"PLANE Z POSITIONS [{setting['z_unit']}]: " + "  |  ".join(z_labels)
        if z_labels else "PLANE Z POSITIONS: unavailable"
    )
    fig.suptitle(
        f"{compact_title}\n{z_title}\n"
        f"{angle_label} density comparison with shared bins and x-axis",
        fontsize=17,
        fontweight="bold",
    )
    plot_path = output_dir / f"{angle_slug}_gate_density_comparison.png"
    written = int(any(plotted_by_kind.values()))
    if written:
        fig.savefig(plot_path, dpi=160)
    plt.close(fig)

    csv_path = output_dir / f"{angle_slug}_histogram_density.csv"
    pd.DataFrame(histogram_rows).to_csv(csv_path, index=False)
    return csv_path, written


def write_phi_asymmetry_scan(
    frame: pd.DataFrame,
    gates: list[Gate],
    masks: dict[str, pd.Series],
    setting: dict[str, Any],
    output_dir: Path,
    title: str,
) -> tuple[Path, int]:
    """Scan a circular phi cut and compare its preceding/following half-planes."""
    asymmetry_setting = setting["phi_asymmetry"]
    variable = asymmetry_setting["variable"]
    phi, unit = angular_values(
        frame, variable, convert_to_degrees=setting["degrees"],
    )
    finite = np.isfinite(phi)
    period = 360.0 if setting["degrees"] else 2.0 * np.pi
    half_period = period / 2.0
    configured_step = float(asymmetry_setting["cut_step"])
    step = configured_step if setting["degrees"] else np.radians(configured_step)
    # A cut rotated by half a turn swaps left and right, so
    # A(phi_cut + 180 degrees) = -A(phi_cut). Keep one independent set of
    # unoriented dividing lines, centred on zero, without duplicating +90.
    cuts = np.arange(-half_period / 2.0, half_period / 2.0, step)

    selections: list[tuple[str, str, str, np.ndarray]] = []
    for gate in gates:
        selections.append((
            "individual", gate.code, gate.name, masks[gate.code].to_numpy(dtype=bool),
        ))
    if setting["include_combined_exact"]:
        combined_codes = sorted(
            frame["gate_code"].dropna().astype(str).unique(),
            key=lambda code: int(code),
        )
        for code in combined_codes:
            if code == "0" and not setting["include_combined_zero"]:
                continue
            selections.append((
                "combined_exact", code, combined_name(code, gates),
                frame["gate_code"].astype(str).eq(code).to_numpy(dtype=bool),
            ))

    rows: list[dict[str, Any]] = []
    plot_kinds = (
        ("individual", "combined_exact")
        if setting["include_combined_exact"] else ("individual",)
    )
    fig, raw_axes = plt.subplots(
        len(plot_kinds), 1, figsize=(15, 11 if len(plot_kinds) == 2 else 6.5),
        constrained_layout=True, sharex=True, sharey=True,
    )
    axes = np.atleast_1d(raw_axes)
    axes_by_kind = dict(zip(plot_kinds, axes, strict=True))
    plotted_by_kind = {kind: 0 for kind in plot_kinds}
    plotted_curves: list[tuple[str, str, np.ndarray]] = []
    for kind, code, name, gate_mask in selections:
        values = phi[finite & gate_mask]
        if not values.size:
            continue
        asymmetries: list[float] = []
        for cut in cuts:
            relative_phi = (values - cut + half_period) % period - half_period
            left_count = int(np.count_nonzero(relative_phi < 0.0))
            right_count = int(values.size - left_count)
            denominator = left_count + right_count
            asymmetry = (
                (left_count - right_count) / denominator
                if denominator else np.nan
            )
            asymmetries.append(asymmetry)
            rows.append({
                "kind": kind,
                "gate_code": code,
                "gate_name": name,
                "phi_cut": float(cut),
                "phi_unit": unit,
                "left_events": left_count,
                "right_events": right_count,
                "total_events": denominator,
                "asymmetry": float(asymmetry),
                "asymmetry_percent": float(100.0 * asymmetry),
            })
        legend_name = (
            next(gate.short_label or gate.name for gate in gates if gate.code == code)
            if kind == "individual" else combined_short_label(code, gates)
        )
        legend_label = f"{legend_name} (n={values.size:,})"
        asymmetry_values = np.asarray(asymmetries, dtype=float)
        axes_by_kind[kind].plot(
            cuts, asymmetry_values, linewidth=1.6, label=legend_label,
        )
        plotted_curves.append((kind, legend_label, asymmetry_values))
        plotted_by_kind[kind] += 1

    axes[0].set(
        xlabel=f"Phi cut [{unit}]" if len(plot_kinds) == 1 else None,
        ylabel="Asymmetry (N_left − N_right) / (N_left + N_right)",
        title="Individual gates (events may appear in more than one curve)",
    )
    if len(plot_kinds) == 2:
        axes[1].set(
            xlabel=f"Phi cut [{unit}]",
            ylabel="Asymmetry (N_left − N_right) / (N_left + N_right)",
            title="Exact combined gate codes (mutually exclusive)",
        )
    for kind, axis in axes_by_kind.items():
        axis.axhline(0.0, color="0.25", linewidth=1.0, linestyle="--")
        axis.grid(True, alpha=0.25)
        axis.set_ylim(-1.0, 1.0)
        if plotted_by_kind[kind]:
            axis.legend(fontsize=7, ncols=2)
        else:
            axis.text(
                0.5, 0.5, "No populated gates", ha="center", va="center",
                transform=axis.transAxes,
            )
    title_parts = [part.strip() for part in title.split("|")]
    compact_title = " | ".join(title_parts[:3])
    z_labels: list[str] = []
    for plane, column in enumerate(setting["z_columns"], 1):
        z_values = pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype=float)
        finite_z = z_values[np.isfinite(z_values)]
        if not len(finite_z):
            label = "n/a"
        else:
            lower_z, upper_z = float(np.min(finite_z)), float(np.max(finite_z))
            label = f"{lower_z:g}" if np.isclose(lower_z, upper_z) else f"{lower_z:g}–{upper_z:g}"
        z_labels.append(f"P{plane}={label}")
    z_title = (
        f"PLANE Z POSITIONS [{setting['z_unit']}]: " + "  |  ".join(z_labels)
        if z_labels else "PLANE Z POSITIONS: unavailable"
    )
    half_plane_label = (
        "independent cuts=[−90°, 90°); left=[cut−180°, cut), "
        "right=[cut, cut+180°), with angular wraparound"
        if setting["degrees"] else
        "independent cuts=[−π/2, π/2); left=[cut−π, cut), "
        "right=[cut, cut+π), with angular wraparound"
    )
    fig.suptitle(
        f"{compact_title}\n{z_title}\nCircular phi-cut asymmetry scan\n"
        f"{half_plane_label}",
        fontsize=16,
        fontweight="bold",
    )
    plot_path = output_dir / "phi_left_right_asymmetry_scan.png"
    written = int(any(plotted_by_kind.values()))
    if written:
        fig.savefig(plot_path, dpi=160)
    plt.close(fig)

    if written and asymmetry_setting.get("plot_percentage", True):
        percent_fig, percent_raw_axes = plt.subplots(
            len(plot_kinds), 1,
            figsize=(15, 11 if len(plot_kinds) == 2 else 6.5),
            constrained_layout=True, sharex=True, sharey=True,
        )
        percent_axes = np.atleast_1d(percent_raw_axes)
        percent_axes_by_kind = dict(zip(plot_kinds, percent_axes, strict=True))
        for kind, legend_label, asymmetry_values in plotted_curves:
            percent_axes_by_kind[kind].plot(
                cuts, 100.0 * asymmetry_values, linewidth=1.6,
                label=legend_label,
            )
        percent_axes[0].set(
            xlabel=f"Phi cut [{unit}]" if len(plot_kinds) == 1 else None,
            ylabel="Asymmetry [%]",
            title="Individual gates (events may appear in more than one curve)",
        )
        if len(plot_kinds) == 2:
            percent_axes[1].set(
                xlabel=f"Phi cut [{unit}]",
                ylabel="Asymmetry [%]",
                title="Exact combined gate codes (mutually exclusive)",
            )
        percentage_limit = float(asymmetry_setting.get("percentage_limit", 50.0))
        for kind, axis in percent_axes_by_kind.items():
            axis.axhline(0.0, color="0.25", linewidth=1.0, linestyle="--")
            axis.grid(True, alpha=0.25)
            axis.set_ylim(-percentage_limit, percentage_limit)
            if plotted_by_kind[kind]:
                axis.legend(fontsize=7, ncols=2)
            else:
                axis.text(
                    0.5, 0.5, "No populated gates", ha="center", va="center",
                    transform=axis.transAxes,
                )
        percent_fig.suptitle(
            f"{compact_title}\n{z_title}\nCircular phi-cut asymmetry scan [%]\n"
            f"{half_plane_label}",
            fontsize=16,
            fontweight="bold",
        )
        percent_fig.savefig(
            output_dir / "phi_left_right_asymmetry_percentage_scan.png",
            dpi=160,
        )
        plt.close(percent_fig)
        written += 1

    csv_path = output_dir / "phi_left_right_asymmetry_scan.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    return csv_path, written


def write_angular_histograms(
    frame: pd.DataFrame,
    gates: list[Gate],
    masks: dict[str, pd.Series],
    setting: dict[str, Any],
    output_dir: Path,
    title: str,
) -> tuple[list[Path], int]:
    results = [
        write_angular_histogram_comparison(
            frame, gates, masks, setting, variable, output_dir, title,
        )
        for variable in setting["variables"]
    ]
    if setting["phi_asymmetry"] is not None:
        results.append(
            write_phi_asymmetry_scan(frame, gates, masks, setting, output_dir, title)
        )
    return [csv_path for csv_path, _ in results], sum(written for _, written in results)



def _streamed_angular_selections(
    aggregates: StreamingAngularHistograms,
    gates: list[Gate],
    slug: str,
) -> list[tuple[str, str, str]]:
    selections = [
        ("individual", gate.code, gate.name) for gate in gates
    ]
    if aggregates.setting["include_combined_exact"]:
        combined_codes = sorted({
            code for key_slug, kind, code in aggregates.histogram_counts
            if key_slug == slug and kind == "combined_exact"
        }, key=int)
        selections.extend(
            ("combined_exact", code, combined_name(code, gates))
            for code in combined_codes
            if code != "0" or aggregates.setting["include_combined_zero"]
        )
    return selections


def _streamed_angular_z_title(
    aggregates: StreamingAngularHistograms,
    setting: dict[str, Any],
) -> str:
    labels: list[str] = []
    for plane, column in enumerate(setting["z_columns"], 1):
        value_range = aggregates.z_ranges.get(column)
        if value_range is None:
            label = "n/a"
        else:
            lower, upper = value_range
            label = f"{lower:g}" if np.isclose(lower, upper) else f"{lower:g}–{upper:g}"
        labels.append(f"P{plane}={label}")
    return (
        f"PLANE Z POSITIONS [{setting['z_unit']}]: " + "  |  ".join(labels)
        if labels else "PLANE Z POSITIONS: unavailable"
    )


def write_streamed_angular_histogram_comparison(
    aggregates: StreamingAngularHistograms,
    gates: list[Gate],
    setting: dict[str, Any],
    variable: dict[str, Any],
    output_dir: Path,
    title: str,
) -> tuple[Path, int]:
    slug = variable["slug"]
    unit = "degrees" if setting["degrees"] else "radians"
    edges = np.linspace(variable["range"][0], variable["range"][1], variable["bins"] + 1)
    widths = np.diff(edges)
    selections = _streamed_angular_selections(aggregates, gates, slug)
    plot_kinds = (
        ("individual", "combined_exact")
        if setting["include_combined_exact"] else ("individual",)
    )
    fig, raw_axes = plt.subplots(
        len(plot_kinds), 1,
        figsize=(15, 11 if len(plot_kinds) == 2 else 6.5),
        constrained_layout=True, sharex=True,
    )
    axes = np.atleast_1d(raw_axes)
    axes_by_kind = dict(zip(plot_kinds, axes, strict=True))
    plotted = {kind: 0 for kind in plot_kinds}
    rows: list[dict[str, Any]] = []
    for kind, code, name in selections:
        key = (slug, kind, code)
        counts = aggregates.histogram_counts.get(
            key, np.zeros(variable["bins"], dtype=np.int64),
        )
        finite_events = int(aggregates.finite_counts.get(key, 0))
        in_range_events = int(counts.sum())
        density = (
            counts.astype(float) / (in_range_events * widths)
            if in_range_events else np.zeros_like(widths)
        )
        for index, count in enumerate(counts):
            rows.append({
                "kind": kind,
                "gate_code": code,
                "gate_name": name,
                "bin_left": edges[index],
                "bin_right": edges[index + 1],
                "events": int(count),
                "density": float(density[index]),
                "finite_events": finite_events,
                "in_range_events": in_range_events,
            })
        if not in_range_events:
            print(f"Warning: no in-range {variable['label']} values for {kind} gate {code}")
            continue
        legend = (
            next(g.short_label or g.name for g in gates if g.code == code)
            if kind == "individual" else combined_short_label(code, gates)
        )
        axes_by_kind[kind].stairs(
            density, edges, linewidth=1.5,
            label=f"{legend} (n={in_range_events:,})",
        )
        plotted[kind] += 1

    axes[0].set(
        xlabel=f"{slug} [{unit}]" if len(plot_kinds) == 1 else None,
        ylabel=f"Probability density [1/{unit}]",
        title="Individual gates (events may appear in more than one curve)",
    )
    if len(plot_kinds) == 2:
        axes[1].set(
            xlabel=f"{slug} [{unit}]", ylabel=f"Probability density [1/{unit}]",
            title="Exact combined gate codes (mutually exclusive)",
        )
    for kind, axis in axes_by_kind.items():
        axis.grid(True, alpha=0.25)
        if plotted[kind]:
            axis.legend(fontsize=7, ncols=2)
        else:
            axis.text(0.5, 0.5, "No populated gates", ha="center", va="center", transform=axis.transAxes)
    compact_title = " | ".join(part.strip() for part in title.split("|")[:3])
    fig.suptitle(
        f"{compact_title}\n{_streamed_angular_z_title(aggregates, setting)}\n"
        f"{variable['label']} density comparison with shared bins and x-axis",
        fontsize=17, fontweight="bold",
    )
    plot_path = output_dir / f"{slug}_gate_density_comparison.png"
    written = int(any(plotted.values()))
    if written:
        fig.savefig(plot_path, dpi=160)
    plt.close(fig)
    csv_path = output_dir / f"{slug}_histogram_density.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    return csv_path, written


def write_streamed_phi_asymmetry_scan(
    aggregates: StreamingAngularHistograms,
    gates: list[Gate],
    setting: dict[str, Any],
    output_dir: Path,
    title: str,
) -> tuple[Path, int]:
    asymmetry_setting = setting["phi_asymmetry"]
    variable = asymmetry_setting["variable"]
    slug = variable["slug"]
    unit = "degrees" if setting["degrees"] else "radians"
    period = 360.0 if setting["degrees"] else 2.0 * np.pi
    half_period = period / 2.0
    configured_step = float(asymmetry_setting["cut_step"])
    step = configured_step if setting["degrees"] else np.radians(configured_step)
    cuts = np.arange(-half_period / 2.0, half_period / 2.0, step)
    selections = _streamed_angular_selections(aggregates, gates, slug)
    plot_kinds = (
        ("individual", "combined_exact")
        if setting["include_combined_exact"] else ("individual",)
    )
    fig, raw_axes = plt.subplots(
        len(plot_kinds), 1,
        figsize=(15, 11 if len(plot_kinds) == 2 else 6.5),
        constrained_layout=True, sharex=True, sharey=True,
    )
    axes = np.atleast_1d(raw_axes)
    axes_by_kind = dict(zip(plot_kinds, axes, strict=True))
    plotted = {kind: 0 for kind in plot_kinds}
    curves: list[tuple[str, str, np.ndarray]] = []
    rows: list[dict[str, Any]] = []
    for kind, code, name in selections:
        key = (kind, code)
        total = int(aggregates.asymmetry_totals.get(key, 0))
        if not total:
            continue
        left = aggregates.asymmetry_left_counts[key]
        right = total - left
        values = (left - right) / total
        for cut, left_count, right_count, asymmetry in zip(cuts, left, right, values, strict=True):
            rows.append({
                "kind": kind, "gate_code": code, "gate_name": name,
                "phi_cut": float(cut), "phi_unit": unit,
                "left_events": int(left_count), "right_events": int(right_count),
                "total_events": total, "asymmetry": float(asymmetry),
                "asymmetry_percent": float(100.0 * asymmetry),
            })
        legend = (
            next(g.short_label or g.name for g in gates if g.code == code)
            if kind == "individual" else combined_short_label(code, gates)
        )
        legend = f"{legend} (n={total:,})"
        axes_by_kind[kind].plot(cuts, values, linewidth=1.6, label=legend)
        curves.append((kind, legend, values))
        plotted[kind] += 1

    axes[0].set(
        xlabel=f"Phi cut [{unit}]" if len(plot_kinds) == 1 else None,
        ylabel="Asymmetry (N_left − N_right) / (N_left + N_right)",
        title="Individual gates (events may appear in more than one curve)",
    )
    if len(plot_kinds) == 2:
        axes[1].set(
            xlabel=f"Phi cut [{unit}]",
            ylabel="Asymmetry (N_left − N_right) / (N_left + N_right)",
            title="Exact combined gate codes (mutually exclusive)",
        )
    for kind, axis in axes_by_kind.items():
        axis.axhline(0.0, color="0.25", linewidth=1.0, linestyle="--")
        axis.grid(True, alpha=0.25)
        axis.set_ylim(-1.0, 1.0)
        if plotted[kind]:
            axis.legend(fontsize=7, ncols=2)
    compact_title = " | ".join(part.strip() for part in title.split("|")[:3])
    z_title = _streamed_angular_z_title(aggregates, setting)
    half_plane_label = (
        "independent cuts=[−90°, 90°); left=[cut−180°, cut), right=[cut, cut+180°), with angular wraparound"
        if setting["degrees"] else
        "independent cuts=[−π/2, π/2); left=[cut−π, cut), right=[cut, cut+π), with angular wraparound"
    )
    fig.suptitle(
        f"{compact_title}\n{z_title}\nCircular phi-cut asymmetry scan\n{half_plane_label}",
        fontsize=16, fontweight="bold",
    )
    written = int(any(plotted.values()))
    if written:
        fig.savefig(output_dir / "phi_left_right_asymmetry_scan.png", dpi=160)
    plt.close(fig)

    if written and asymmetry_setting.get("plot_percentage", True):
        percent_fig, percent_raw_axes = plt.subplots(
            len(plot_kinds), 1,
            figsize=(15, 11 if len(plot_kinds) == 2 else 6.5),
            constrained_layout=True, sharex=True, sharey=True,
        )
        percent_axes = np.atleast_1d(percent_raw_axes)
        percent_by_kind = dict(zip(plot_kinds, percent_axes, strict=True))
        for kind, legend, values in curves:
            percent_by_kind[kind].plot(cuts, 100.0 * values, linewidth=1.6, label=legend)
        percent_axes[0].set(
            xlabel=f"Phi cut [{unit}]" if len(plot_kinds) == 1 else None,
            ylabel="Asymmetry [%]",
            title="Individual gates (events may appear in more than one curve)",
        )
        if len(plot_kinds) == 2:
            percent_axes[1].set(
                xlabel=f"Phi cut [{unit}]", ylabel="Asymmetry [%]",
                title="Exact combined gate codes (mutually exclusive)",
            )
        limit = float(asymmetry_setting.get("percentage_limit", 50.0))
        for kind, axis in percent_by_kind.items():
            axis.axhline(0.0, color="0.25", linewidth=1.0, linestyle="--")
            axis.grid(True, alpha=0.25)
            axis.set_ylim(-limit, limit)
            if plotted[kind]:
                axis.legend(fontsize=7, ncols=2)
        percent_fig.suptitle(
            f"{compact_title}\n{z_title}\nCircular phi-cut asymmetry scan [%]\n{half_plane_label}",
            fontsize=16, fontweight="bold",
        )
        percent_fig.savefig(output_dir / "phi_left_right_asymmetry_percentage_scan.png", dpi=160)
        plt.close(percent_fig)
        written += 1
    csv_path = output_dir / "phi_left_right_asymmetry_scan.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    return csv_path, written


def write_streamed_angular_histograms(
    aggregates: StreamingAngularHistograms,
    gates: list[Gate],
    setting: dict[str, Any],
    output_dir: Path,
    title: str,
) -> tuple[list[Path], int]:
    results = [
        write_streamed_angular_histogram_comparison(
            aggregates, gates, setting, variable, output_dir, title,
        )
        for variable in setting["variables"]
    ]
    if setting["phi_asymmetry"] is not None:
        results.append(
            write_streamed_phi_asymmetry_scan(
                aggregates, gates, setting, output_dir, title,
            )
        )
    return [csv_path for csv_path, _ in results], sum(written for _, written in results)

def topology_charge_scatter_setting(
    config: dict[str, Any], gates: list[Gate], available: set[str],
) -> dict[str, Any] | None:
    raw = config.get("topology_charge_scatter", {})
    if raw is False:
        return None
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("topology_charge_scatter must be a YAML mapping or false")
    if not bool(raw.get("enabled", True)):
        return None
    gate = gate_from_short_label(
        gates, raw.get("gate_label", gates[0].short_label),
        location="topology_charge_scatter.gate_label",
    )
    gate_code = gate.code
    pattern = str(raw.get("topology", "1001")).strip()
    if not re.fullmatch(r"[01]{4}", pattern):
        raise ValueError("topology_charge_scatter.topology must be four binary digits")
    x_strip = int(raw.get("x_strip", 1))
    y_strip = int(raw.get("y_strip", 4))
    if x_strip not in range(1, 5) or y_strip not in range(1, 5):
        raise ValueError("topology_charge_scatter strip numbers must be in 1..4")
    raw_variables = raw.get("variables", [
        {"suffix": "qsum_cal", "label": "Calibrated Q_sum"},
        {"suffix": "tdif_cal", "label": "Calibrated T_dif"},
        {"suffix": "qdif_cal", "label": "Calibrated Q_dif"},
        {"suffix": "tsum_cal", "label": "Calibrated T_sum"},
    ])
    if not isinstance(raw_variables, list) or not raw_variables:
        raise ValueError("topology_charge_scatter.variables must be a nonempty list")
    variables: list[dict[str, str]] = []
    for index, item in enumerate(raw_variables, 1):
        if not isinstance(item, dict) or not str(item.get("suffix", "")).strip():
            raise ValueError(f"topology_charge_scatter.variables item {index} needs suffix")
        suffix = str(item["suffix"]).strip()
        label = str(item.get("label", suffix)).strip()
        if suffix in {variable["suffix"] for variable in variables}:
            raise ValueError(f"Duplicate topology scatter variable suffix: {suffix}")
        variables.append({"suffix": suffix, "label": label})
    columns = [
        f"p{plane}_s{strip}_{variable["suffix"]}"
        for variable in variables
        for plane in range(1, 5)
        for strip in (x_strip, y_strip)
    ]
    missing = sorted(set(columns) - available)
    if missing:
        raise ValueError("Topology scatter columns absent: " + ", ".join(missing))
    maximum = int(raw.get("max_points_per_file", 25000))
    if maximum < 1:
        raise ValueError("topology_charge_scatter.max_points_per_file must be positive")
    quantiles = raw.get("plot_quantiles", [0.001, 0.999])
    if not isinstance(quantiles, (list, tuple)) or len(quantiles) != 2:
        raise ValueError("topology_charge_scatter.plot_quantiles needs two values")
    low, high = float(quantiles[0]), float(quantiles[1])
    if not 0 <= low < high <= 1:
        raise ValueError("Topology scatter quantiles must satisfy 0 <= low < high <= 1")
    return {
        "gate_code": gate_code,
        "gate_label": gate.short_label,
        "pattern": pattern,
        "x_strip": x_strip,
        "y_strip": y_strip,
        "variables": variables,
        "columns": columns,
        "maximum": maximum,
        "quantiles": (low, high),
    }


def topology_y_position_setting(
    config: dict[str, Any], gates: list[Gate], available: set[str],
) -> dict[str, Any] | None:
    raw = config.get("topology_y_position", {})
    if raw is False:
        return None
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("topology_y_position must be a YAML mapping or false")
    if not bool(raw.get("enabled", True)):
        return None
    gate = gate_from_short_label(
        gates, raw.get("gate_label", gates[0].short_label),
        location="topology_y_position.gate_label",
    )
    gate_code = gate.code
    pattern = str(raw.get("topology", "1001")).strip()
    if not re.fullmatch(r"[01]{4}", pattern):
        raise ValueError("topology_y_position.topology must be four binary digits")
    time_column = str(raw.get("time_column", "datetime")).strip()
    y_columns = [f"p{plane}_ypos" for plane in range(1, 5)]
    first_strip = int(raw.get("first_strip", 1))
    second_strip = int(raw.get("second_strip", 4))
    if first_strip not in range(1, 5) or second_strip not in range(1, 5) or first_strip == second_strip:
        raise ValueError("topology_y_position strips must be distinct values in 1..4")
    charge_suffix = str(raw.get("charge_suffix", "qsum_cal")).strip()
    charge_columns = [
        f"p{plane}_s{strip}_{charge_suffix}"
        for plane in range(1, 5) for strip in (first_strip, second_strip)
    ]
    columns = [time_column, *y_columns, *charge_columns]
    missing = sorted(set(columns) - available)
    if missing:
        raise ValueError("Topology Y-position columns absent: " + ", ".join(missing))
    bins = int(raw.get("bins", 80))
    if bins < 1:
        raise ValueError("topology_y_position.bins must be positive")
    value_range = raw.get("range", [-150, 150])
    if not isinstance(value_range, (list, tuple)) or len(value_range) != 2:
        raise ValueError("topology_y_position.range must contain [minimum, maximum]")
    lower, upper = float(value_range[0]), float(value_range[1])
    if lower >= upper:
        raise ValueError("topology_y_position.range must be increasing")
    maximum = int(raw.get("max_scatter_points_per_plane", 100000))
    if maximum < 1:
        raise ValueError("topology_y_position.max_scatter_points_per_plane must be positive")
    return {
        "gate_code": gate_code,
        "gate_label": gate.short_label,
        "pattern": pattern,
        "time_column": time_column,
        "y_columns": y_columns,
        "first_strip": first_strip,
        "second_strip": second_strip,
        "charge_suffix": charge_suffix,
        "charge_columns": charge_columns,
        "columns": columns,
        "bins": bins,
        "range": (lower, upper),
        "maximum": maximum,
        "omit_zero": bool(raw.get("omit_zero", False)),
    }


def expand_topology_diagnostic_settings(
    config: dict[str, Any],
    gates: list[Gate],
    available: set[str],
    charge_base: dict[str, Any] | None,
    y_base: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if charge_base is None and y_base is None:
        return [], []
    base = charge_base if charge_base is not None else y_base
    targets: list[dict[str, Any]] = [{
        "gate_label": base["gate_label"],
        "topology": base["pattern"],
        "first_strip": (
            charge_base["x_strip"] if charge_base is not None else y_base["first_strip"]
        ),
        "second_strip": (
            charge_base["y_strip"] if charge_base is not None else y_base["second_strip"]
        ),
    }]
    additional = config.get("additional_topology_diagnostic_targets", [])
    if additional is None:
        additional = []
    if not isinstance(additional, list):
        raise ValueError("additional_topology_diagnostic_targets must be a list")
    targets.extend(additional)

    seen: set[tuple[str, str]] = set()
    charge_settings: list[dict[str, Any]] = []
    y_settings: list[dict[str, Any]] = []
    for index, target in enumerate(targets, 1):
        if not isinstance(target, dict):
            raise ValueError(f"Topology diagnostic target {index} must be a mapping")
        gate = gate_from_short_label(
            gates, target.get("gate_label", ""),
            location=f"additional_topology_diagnostic_targets item {index}.gate_label",
        )
        gate_code = gate.code
        pattern = str(target.get("topology", "")).strip()
        first_strip = int(target.get("first_strip", 0))
        second_strip = int(target.get("second_strip", 0))
        if not re.fullmatch(r"[01]{4}", pattern):
            raise ValueError(f"Topology diagnostic target has invalid topology {pattern!r}")
        if first_strip not in range(1, 5) or second_strip not in range(1, 5) or first_strip == second_strip:
            raise ValueError("Topology diagnostic target strips must be distinct values in 1..4")
        expected_pattern = "".join(
            "1" if strip in {first_strip, second_strip} else "0"
            for strip in range(1, 5)
        )
        if pattern != expected_pattern:
            raise ValueError(
                f"Topology {pattern} does not match active strips {first_strip},{second_strip}"
            )
        key = (gate_code, pattern)
        if key in seen:
            raise ValueError(f"Duplicate topology diagnostic target: gate {gate_code}, {pattern}")
        seen.add(key)

        if charge_base is not None:
            charge_setting = dict(charge_base)
            charge_setting.update(
                gate_code=gate_code, gate_label=gate.short_label, pattern=pattern,
                x_strip=first_strip, y_strip=second_strip,
            )
            charge_columns = [
                f"p{plane}_s{strip}_{variable['suffix']}"
                for variable in charge_setting["variables"]
                for plane in range(1, 5)
                for strip in (first_strip, second_strip)
            ]
            missing = sorted(set(charge_columns) - available)
            if missing:
                raise ValueError("Topology scatter columns absent: " + ", ".join(missing))
            charge_setting["columns"] = charge_columns
            raw_limits = target.get("diagonal_limits", {})
            if raw_limits is None:
                raw_limits = {}
            if not isinstance(raw_limits, dict):
                raise ValueError("Topology diagnostic diagonal_limits must be a mapping")
            known_suffixes = {variable["suffix"] for variable in charge_setting["variables"]}
            unknown_limits = sorted(set(raw_limits) - known_suffixes)
            if unknown_limits:
                raise ValueError(
                    "Topology diagnostic limits use unknown variables: "
                    + ", ".join(unknown_limits)
                )
            diagonal_limits = {key: float(value) for key, value in raw_limits.items()}
            if any(not np.isfinite(value) or value <= 0 for value in diagonal_limits.values()):
                raise ValueError("Topology diagnostic diagonal limits must be finite and positive")
            charge_setting["diagonal_limits"] = diagonal_limits
            charge_settings.append(charge_setting)

        if y_base is not None:
            y_setting = dict(y_base)
            charge_suffix = y_setting["charge_suffix"]
            y_charge_columns = [
                f"p{plane}_s{strip}_{charge_suffix}"
                for plane in range(1, 5)
                for strip in (first_strip, second_strip)
            ]
            y_columns = [
                y_setting["time_column"],
                *y_setting["y_columns"],
                *y_charge_columns,
            ]
            missing = sorted(set(y_columns) - available)
            if missing:
                raise ValueError("Topology Y-position columns absent: " + ", ".join(missing))
            y_setting.update(
                gate_code=gate_code, gate_label=gate.short_label, pattern=pattern,
                first_strip=first_strip, second_strip=second_strip,
                charge_columns=y_charge_columns, columns=y_columns,
            )
            y_settings.append(y_setting)
    return charge_settings, y_settings


def write_topology_charge_scatter(
    frame: pd.DataFrame,
    files: list[Product],
    masks: dict[str, pd.Series],
    setting: dict[str, Any],
    output_dir: Path,
    title: str,
) -> tuple[Path, Path, int]:
    gate_code = setting["gate_code"]
    gate_label = setting["gate_label"]
    pattern = setting["pattern"]
    x_strip = setting["x_strip"]
    y_strip = setting["y_strip"]
    variables = setting["variables"]
    maximum = setting["maximum"]
    quantiles = setting["quantiles"]
    diagonal_limits = setting.get("diagonal_limits", {})
    fig, axes = plt.subplots(
        len(variables), 4, figsize=(19, 4.3 * len(variables)),
        constrained_layout=True, squeeze=False,
    )
    colors = plt.get_cmap("tab10").colors
    summary_rows: list[dict[str, Any]] = []
    range_values: dict[str, list[np.ndarray]] = {
        variable["suffix"]: [] for variable in variables
    }
    plotted = 0
    legend_handles = None
    legend_labels = None
    gate_mask = masks[gate_code]

    for row_index, variable in enumerate(variables):
        suffix = variable["suffix"]
        label = variable["label"]
        for plane in range(1, 5):
            axis = axes[row_index, plane - 1]
            topology_mask = frame[f"p{plane}_strip_topology"].astype(str).eq(pattern)
            plane_mask = gate_mask & topology_mask
            x_column = f"p{plane}_s{x_strip}_{suffix}"
            y_column = f"p{plane}_s{y_strip}_{suffix}"
            joined = frame.loc[plane_mask, [x_column, y_column]].apply(
                pd.to_numeric, errors="coerce",
            )
            joined = joined.loc[
                np.isfinite(joined[x_column])
                & np.isfinite(joined[y_column])
                & joined[x_column].ne(0)
                & joined[y_column].ne(0)
            ]
            joined_correlation = (
                joined[x_column].corr(joined[y_column]) if len(joined) > 1 else np.nan
            )
            summary_rows.append({
                "variable": suffix,
                "plane": plane,
                "source": "joined",
                "events": len(joined),
                f"strip_{x_strip}_median": joined[x_column].median() if len(joined) else np.nan,
                f"strip_{y_strip}_median": joined[y_column].median() if len(joined) else np.nan,
                "pearson_correlation": joined_correlation,
            })
            if not joined.empty:
                range_values[suffix].extend([
                    joined[x_column].to_numpy(dtype=float),
                    joined[y_column].to_numpy(dtype=float),
                ])
            panel_points = 0
            for file_index, product in enumerate(files):
                source_mask = plane_mask & frame["_source_basename"].eq(product.basename)
                part = frame.loc[source_mask, [x_column, y_column]].apply(
                    pd.to_numeric, errors="coerce",
                )
                part = part.loc[
                    np.isfinite(part[x_column])
                    & np.isfinite(part[y_column])
                    & part[x_column].ne(0)
                    & part[y_column].ne(0)
                ]
                correlation = part[x_column].corr(part[y_column]) if len(part) > 1 else np.nan
                summary_rows.append({
                    "variable": suffix,
                    "plane": plane,
                    "source": product.basename,
                    "events": len(part),
                    f"strip_{x_strip}_median": part[x_column].median() if len(part) else np.nan,
                    f"strip_{y_strip}_median": part[y_column].median() if len(part) else np.nan,
                    "pearson_correlation": correlation,
                })
                if len(part) > maximum:
                    part = part.sample(
                        maximum,
                        random_state=4100 + 100 * row_index + 10 * plane + file_index,
                    )
                if part.empty:
                    continue
                axis.scatter(
                    part[x_column], part[y_column], s=6, alpha=0.30, linewidths=0,
                    color=colors[file_index % len(colors)], label=product.basename,
                    rasterized=True,
                )
                panel_points += len(part)
                plotted += len(part)
            if row_index == 0:
                axis.set_title(f"Plane {plane}", fontsize=12)
            axis.text(
                0.98, 0.97, f"n={len(joined):,}", ha="right", va="top",
                transform=axis.transAxes, fontsize=8,
            )
            axis.set_xlabel(f"Strip {x_strip}")
            if plane == 1:
                axis.set_ylabel(f"{label}\nStrip {y_strip}")
            axis.grid(True, alpha=0.25)
            if not panel_points:
                axis.text(
                    0.5, 0.5, "No matching pairs", ha="center", va="center",
                    transform=axis.transAxes,
                )
            if legend_handles is None and panel_points:
                legend_handles, legend_labels = axis.get_legend_handles_labels()

    for row_index, variable in enumerate(variables):
        values_for_row = range_values[variable["suffix"]]
        if not values_for_row:
            continue
        values = np.concatenate(values_for_row)
        low, high = np.quantile(values, quantiles)
        if not np.isfinite(low) or not np.isfinite(high):
            low, high = np.nanmin(values), np.nanmax(values)
        if low == high:
            padding = max(abs(float(low)) * 0.01, 1e-6)
            low, high = low - padding, high + padding
        for axis in axes[row_index, :]:
            axis.set_xlim(float(low), float(high))
            axis.set_ylim(float(low), float(high))
            axis.plot(
                [low, high], [low, high], linestyle="--", linewidth=0.8,
                color="black", alpha=0.6,
            )
            limit = diagonal_limits.get(variable["suffix"])
            if limit is not None:
                diagonal = np.asarray([low, high], dtype=float)
                axis.fill_between(
                    diagonal, diagonal - limit, diagonal + limit,
                    color="red", alpha=0.10, zorder=2,
                )
                axis.plot(
                    diagonal, diagonal - limit, color="red", linewidth=1.2,
                    zorder=3,
                )
                axis.plot(
                    diagonal, diagonal + limit, color="red", linewidth=1.2,
                    zorder=3,
                )
                axis.text(
                    0.02, 0.97, f"|Δ| < {limit:g}", color="red",
                    ha="left", va="top", transform=axis.transAxes, fontsize=8,
                )

    fig.suptitle(
        f"{title}\nGate {gate_label} [{gate_code}], per-plane topology {pattern}: "
        f"strip {y_strip} versus strip {x_strip}",
        fontsize=14,
    )
    if legend_handles:
        fig.legend(
            legend_handles, legend_labels, loc="upper right",
            bbox_to_anchor=(0.995, 0.995), fontsize=7,
        )
    plot_path = output_dir / (
        f"gate_{gate_code}_topology_{pattern}_"
        f"strip_{y_strip}_vs_{x_strip}_variables.png"
    )
    if plotted:
        fig.savefig(plot_path, dpi=160)
    plt.close(fig)
    summary_path = output_dir / (
        f"gate_{gate_code}_topology_{pattern}_variable_summary.csv"
    )
    pd.DataFrame(summary_rows).to_csv(summary_path, index=False)
    return plot_path, summary_path, int(plotted > 0)


def write_topology_y_position(
    frame: pd.DataFrame,
    files: list[Product],
    masks: dict[str, pd.Series],
    setting: dict[str, Any],
    output_dir: Path,
    title: str,
) -> tuple[Path, Path, Path, int]:
    gate_code = setting["gate_code"]
    gate_label = setting["gate_label"]
    pattern = setting["pattern"]
    time_column = setting["time_column"]
    first_strip = setting["first_strip"]
    second_strip = setting["second_strip"]
    charge_suffix = setting["charge_suffix"]
    lower, upper = setting["range"]
    position_fig, position_axes = plt.subplots(
        2, 4, figsize=(20, 9), constrained_layout=True, squeeze=False,
    )
    event_rows: list[pd.DataFrame] = []
    total_events = 0
    gate_mask = masks[gate_code]
    for plane in range(1, 5):
        topology_mask = frame[f"p{plane}_strip_topology"].astype(str).eq(pattern)
        plane_mask = gate_mask & topology_mask
        y_column = f"p{plane}_ypos"
        first_column = f"p{plane}_s{first_strip}_{charge_suffix}"
        second_column = f"p{plane}_s{second_strip}_{charge_suffix}"
        values = pd.to_numeric(frame.loc[plane_mask, y_column], errors="coerce")
        first_charge = pd.to_numeric(frame.loc[plane_mask, first_column], errors="coerce")
        second_charge = pd.to_numeric(frame.loc[plane_mask, second_column], errors="coerce")
        charge_total = first_charge + second_charge
        times = pd.to_datetime(frame.loc[plane_mask, time_column], errors="coerce")
        sources = frame.loc[plane_mask, "_source_basename"].astype(str)
        valid = (
            values.notna() & np.isfinite(values)
            & first_charge.notna() & np.isfinite(first_charge)
            & second_charge.notna() & np.isfinite(second_charge)
            & charge_total.ne(0) & times.notna()
        )
        if setting["omit_zero"]:
            valid &= values.ne(0)
        data = pd.DataFrame({
            "datetime": times.loc[valid],
            "source_basename": sources.loc[valid],
            "gate_code": gate_code,
            "gate_label": gate_label,
            "plane_topology": pattern,
            "plane": plane,
            "y_position": values.loc[valid],
            f"charge_strip_{first_strip}": first_charge.loc[valid],
            f"charge_strip_{second_strip}": second_charge.loc[valid],
            "charge_pair_sum": charge_total.loc[valid],
            f"charge_fraction_strip_{first_strip}": (
                first_charge.loc[valid] / charge_total.loc[valid]
            ),
            "charge_asymmetry": (
                (first_charge.loc[valid] - second_charge.loc[valid])
                / charge_total.loc[valid]
            ),
        }).sort_values("datetime")
        event_rows.append(data)
        total_events += len(data)

        time_axis = position_axes[0, plane - 1]
        histogram_axis = position_axes[1, plane - 1]
        scatter_data = data
        if len(scatter_data) > setting["maximum"]:
            scatter_data = scatter_data.sample(
                setting["maximum"], random_state=8100 + plane,
            ).sort_values("datetime")
        if data.empty:
            time_axis.text(0.5, 0.5, "No matching Y values", ha="center", va="center",
                           transform=time_axis.transAxes)
            histogram_axis.text(0.5, 0.5, "No matching Y values", ha="center", va="center",
                                transform=histogram_axis.transAxes)
        else:
            time_axis.scatter(
                scatter_data["datetime"], scatter_data["y_position"],
                s=5, alpha=0.35, linewidths=0, color=f"C{plane - 1}", rasterized=True,
            )
            histogram_axis.hist(
                data["y_position"], bins=setting["bins"], range=(lower, upper),
                color=f"C{plane - 1}", alpha=0.70, edgecolor="black", linewidth=0.35,
            )
            median = float(data["y_position"].median())
            histogram_axis.axvline(
                median, color="crimson", linestyle="--", linewidth=1.2,
                label=f"median={median:.3g}",
            )
            histogram_axis.legend(fontsize=8)
        time_axis.set_title(f"Plane {plane} | n={len(data):,}")
        time_axis.set_xlabel("Time")
        time_axis.set_ylabel("Selected Y position")
        time_axis.set_ylim(lower, upper)
        time_axis.grid(True, alpha=0.25)
        histogram_axis.set_xlabel("Selected Y position")
        histogram_axis.set_ylabel("Events")
        histogram_axis.set_xlim(lower, upper)
        histogram_axis.grid(True, alpha=0.25)

    position_fig.suptitle(
        f"{title} | Gate {gate_label} [{gate_code}], per-plane strip topology {pattern}: selected Y position",
        fontsize=14,
    )
    position_plot_path = (
        output_dir / f"gate_{gate_code}_topology_{pattern}_selected_y_position.png"
    )
    position_fig.savefig(position_plot_path, dpi=160)
    plt.close(position_fig)

    all_data = pd.concat(event_rows, ignore_index=True)
    charge_fig, charge_axes = plt.subplots(
        2, 4, figsize=(20, 10), constrained_layout=True, squeeze=False,
    )
    colored_scatter: Any = None
    fraction_column = f"charge_fraction_strip_{first_strip}"
    for plane in range(1, 5):
        data = all_data.loc[all_data["plane"].eq(plane)]
        fraction_axis = charge_axes[0, plane - 1]
        pair_axis = charge_axes[1, plane - 1]
        scatter_data = data
        if len(scatter_data) > setting["maximum"]:
            scatter_data = scatter_data.sample(
                setting["maximum"], random_state=9100 + plane,
            )
        if data.empty:
            fraction_axis.text(0.5, 0.5, "No matching charge pairs", ha="center", va="center",
                               transform=fraction_axis.transAxes)
            pair_axis.text(0.5, 0.5, "No matching charge pairs", ha="center", va="center",
                           transform=pair_axis.transAxes)
        else:
            fraction_axis.scatter(
                scatter_data[fraction_column], scatter_data["y_position"],
                s=6, alpha=0.30, linewidths=0, color=f"C{plane - 1}", rasterized=True,
            )
            fraction_axis.axvline(0.5, color="black", linestyle="--", linewidth=0.8)
            first_values = scatter_data[f"charge_strip_{first_strip}"]
            second_values = scatter_data[f"charge_strip_{second_strip}"]
            colored_scatter = pair_axis.scatter(
                first_values, second_values, c=scatter_data["y_position"],
                cmap="coolwarm", vmin=lower, vmax=upper, s=7, alpha=0.38,
                linewidths=0, rasterized=True,
            )
            pair_values = np.concatenate([
                data[f"charge_strip_{first_strip}"].to_numpy(dtype=float),
                data[f"charge_strip_{second_strip}"].to_numpy(dtype=float),
            ])
            charge_low, charge_high = np.quantile(pair_values, [0.001, 0.999])
            if charge_low == charge_high:
                padding = max(abs(float(charge_low)) * 0.01, 1e-6)
                charge_low, charge_high = charge_low - padding, charge_high + padding
            pair_axis.set_xlim(float(charge_low), float(charge_high))
            pair_axis.set_ylim(float(charge_low), float(charge_high))
            pair_axis.plot(
                [charge_low, charge_high], [charge_low, charge_high],
                color="black", linestyle="--", linewidth=0.8,
            )
        fraction_axis.set_title(f"Plane {plane} | n={len(data):,}")
        fraction_axis.set_xlabel(
            f"Q(strip {first_strip}) / [Q(strip {first_strip}) + Q(strip {second_strip})]"
        )
        fraction_axis.set_ylabel("Selected Y position")
        fraction_axis.set_xlim(-0.02, 1.02)
        fraction_axis.set_ylim(lower, upper)
        fraction_axis.grid(True, alpha=0.25)
        pair_axis.set_xlabel(f"Q(strip {first_strip})")
        pair_axis.set_ylabel(f"Q(strip {second_strip})")
        pair_axis.grid(True, alpha=0.25)
    if colored_scatter is not None:
        charge_fig.colorbar(
            colored_scatter, ax=charge_axes[1, :].tolist(),
            label="Selected Y position", shrink=0.90,
        )
    charge_fig.suptitle(
        f"{title} | Gate {gate_label} [{gate_code}], topology {pattern}: active-strip charges versus selected Y",
        fontsize=14,
    )
    charge_plot_path = (
        output_dir / f"gate_{gate_code}_topology_{pattern}_charge_fraction_vs_y.png"
    )
    charge_fig.savefig(charge_plot_path, dpi=160)
    plt.close(charge_fig)

    csv_path = output_dir / f"gate_{gate_code}_topology_{pattern}_selected_y_position.csv"
    all_data.to_csv(csv_path, index=False)
    print(
        f"Topology Y/charge diagnostic: gate={gate_label} [{gate_code}], topology={pattern}, "
        f"values={total_events:,}, files={len(files)}"
    )
    return position_plot_path, charge_plot_path, csv_path, 2



def fit_projection_time_series_setting(
    config: dict[str, Any], available: set[str],
) -> dict[str, Any] | None:
    """Validate the event-fit xproj/yproj time-series configuration."""
    raw = config.get("fit_projection_time_series", {})
    if raw is False:
        return None
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("fit_projection_time_series must be a YAML mapping or false")
    if not bool(raw.get("enabled", True)):
        return None

    time_column = str(raw.get("time_column", "datetime")).strip()
    x_column = str(raw.get("xproj_column", "event_xp")).strip()
    y_column = str(raw.get("yproj_column", "event_yp")).strip()
    missing = sorted({time_column, x_column, y_column} - available)
    if missing:
        raise ValueError(
            "Fit-projection time-series columns absent from schema: "
            + ", ".join(missing)
        )
    try:
        window = pd.Timedelta(str(raw.get("accumulation_timespan", "30min")))
    except ValueError as exc:
        raise ValueError(
            "Invalid fit_projection_time_series.accumulation_timespan"
        ) from exc
    if window <= pd.Timedelta(0):
        raise ValueError(
            "fit_projection_time_series.accumulation_timespan must be positive"
        )
    deviation = str(raw.get("deviation", "median_absolute_deviation")).strip().lower()
    deviation = {"mad": "median_absolute_deviation"}.get(deviation, deviation)
    if deviation != "median_absolute_deviation":
        raise ValueError(
            "fit_projection_time_series.deviation must be "
            "'median_absolute_deviation' (or 'mad')"
        )
    return {
        "time_column": time_column,
        "x_column": x_column,
        "y_column": y_column,
        "window": window,
        "deviation": deviation,
    }


def fit_projection_summary(
    frame: pd.DataFrame,
    gates: list[Gate],
    masks: dict[str, pd.Series],
    setting: dict[str, Any],
) -> pd.DataFrame:
    """Return per-gate/window medians and median absolute deviations."""
    columns = [
        "window_start", "window_end", "gate_code", "gate_name", "gate_label",
        "event_count", "xproj_count", "xproj_median", "xproj_mad",
        "yproj_count", "yproj_median", "yproj_mad",
    ]
    timestamps = pd.to_datetime(frame[setting["time_column"]], errors="coerce")
    x_values = pd.to_numeric(frame[setting["x_column"]], errors="coerce")
    y_values = pd.to_numeric(frame[setting["y_column"]], errors="coerce")
    rows: list[dict[str, Any]] = []

    for gate in gates:
        selected = masks[gate.code].fillna(False) & timestamps.notna()
        selected_frame = pd.DataFrame({
            "window_start": timestamps.loc[selected].dt.floor(setting["window"]),
            "xproj": x_values.loc[selected],
            "yproj": y_values.loc[selected],
        })
        for window_start, group in selected_frame.groupby(
            "window_start", sort=True, observed=True,
        ):
            x = group["xproj"].to_numpy(dtype=float)
            y = group["yproj"].to_numpy(dtype=float)
            x = x[np.isfinite(x)]
            y = y[np.isfinite(y)]
            x_median = float(np.median(x)) if x.size else np.nan
            y_median = float(np.median(y)) if y.size else np.nan
            rows.append({
                "window_start": window_start,
                "window_end": window_start + setting["window"],
                "gate_code": gate.code,
                "gate_name": gate.name,
                "gate_label": gate.short_label or gate.name,
                "event_count": int(len(group)),
                "xproj_count": int(x.size),
                "xproj_median": x_median,
                "xproj_mad": (
                    float(np.median(np.abs(x - x_median))) if x.size else np.nan
                ),
                "yproj_count": int(y.size),
                "yproj_median": y_median,
                "yproj_mad": (
                    float(np.median(np.abs(y - y_median))) if y.size else np.nan
                ),
            })
    return pd.DataFrame(rows, columns=columns)


def write_fit_projection_time_series(
    frame: pd.DataFrame,
    gates: list[Gate],
    masks: dict[str, pd.Series],
    setting: dict[str, Any],
    output_dir: Path,
    title: str,
) -> tuple[Path, int]:
    """Write xproj/yproj median +/- MAD time series for every enabled gate."""
    summary = fit_projection_summary(frame, gates, masks, setting)
    csv_path = output_dir / "fit_projection_time_series.csv"
    summary.to_csv(csv_path, index=False)
    plot_count = 0

    for gate in gates:
        data = summary.loc[summary["gate_code"].eq(gate.code)]
        if data.empty:
            print(
                f"Warning: no fit-projection values for gate "
                f"{gate.short_label or gate.name} [{gate.code}]"
            )
            continue
        fig, axes = plt.subplots(
            2, 1, figsize=(16, 9), sharex=True, constrained_layout=True,
        )
        for axis, coordinate, symbol in (
            (axes[0], "xproj", "x'"),
            (axes[1], "yproj", "y'"),
        ):
            valid = (
                data[f"{coordinate}_median"].notna()
                & data[f"{coordinate}_mad"].notna()
            )
            values = data.loc[valid]
            if values.empty:
                axis.text(
                    0.5, 0.5, "No finite fitted projections",
                    ha="center", va="center", transform=axis.transAxes,
                )
            else:
                axis.errorbar(
                    values["window_start"],
                    values[f"{coordinate}_median"],
                    yerr=values[f"{coordinate}_mad"],
                    fmt=".-", markersize=4, linewidth=1.0,
                    elinewidth=0.8, capsize=1.5,
                    label=f"median {symbol} +/- MAD",
                )
                axis.legend()
            axis.axhline(0.0, color="black", linestyle="--", linewidth=0.8)
            axis.set_ylabel(f"{symbol} [slope]")
            axis.set_title(
                f"{symbol} time evolution: median with median absolute deviation"
            )
            axis.grid(True, alpha=0.25)
        axes[-1].set_xlabel("Time")
        fig.suptitle(
            f"{title}\nGate {gate.short_label or gate.name} [{gate.code}] | "
            f"fit projections | accumulation={setting['window']}",
            fontsize=14,
        )
        fig.autofmt_xdate()
        plot_path = (
            output_dir / f"gate_{gate.code}_fit_projection_time_series.png"
        )
        fig.savefig(plot_path, dpi=160)
        plt.close(fig)
        plot_count += 1

    return csv_path, plot_count

def streaming_parameters(
    rate_setting: dict[str, Any] | None,
    burst_setting: dict[str, Any] | None,
    efficiency_setting: dict[str, Any] | None,
    gate_comparison: dict[str, Any] | None,
    plane_combination: dict[str, Any] | None,
    histogram_setting: dict[str, Any] | None,
    fit_projection_setting: dict[str, Any] | None,
    calibration_comparison: dict[str, Any] | None,
    charge_scatter_settings: list[dict[str, Any]],
    y_position_settings: list[dict[str, Any]],
    charge_cluster_setting: dict[str, Any] | None = None,
    plane_xy_setting: dict[str, Any] | None = None,
    plane_efficiency_setting: dict[str, Any] | None = None,
    incompatibilities: list[str] | None = None,
) -> tuple[str, str, pd.Timedelta] | None:
    """Return a shared exact streaming layout, or None for event-level analyses."""
    blockers = [
        name
        for name, enabled in (
            ("one_second_burst_diagnostics", burst_setting is not None),
            ("plane_combinations", plane_combination is not None),
            ("fit_projection_time_series", fit_projection_setting is not None),
            ("charge_calibration_comparison", calibration_comparison is not None),
            ("topology_charge_scatter", bool(charge_scatter_settings)),
            ("topology_y_position", bool(y_position_settings)),
        )
        if enabled
    ]
    if blockers:
        if incompatibilities is not None:
            incompatibilities.extend(
                f"{name}: requires event-level data" for name in blockers
            )
        return None
    layouts: list[tuple[str, str, str, pd.Timedelta]] = []
    if rate_setting is not None:
        layouts.append((
            "time_series",
            rate_setting["column"],
            "",
            rate_setting["window"],
        ))
    if efficiency_setting is not None:
        layouts.append((
            "efficiency_time_series",
            efficiency_setting["time_column"],
            efficiency_setting["topology_column"],
            efficiency_setting["window"],
        ))
    if gate_comparison is not None:
        layouts.append((
            "enabled_gate_comparison",
            gate_comparison["time_column"],
            gate_comparison["topology_column"],
            gate_comparison["window"],
        ))
    if not layouts:
        if (
            histogram_setting is not None
            or charge_cluster_setting is not None
            or plane_xy_setting is not None
            or plane_efficiency_setting is not None
        ):
            return (
                "",
                (
                    plane_efficiency_setting["topology_column"]
                    if plane_efficiency_setting is not None
                    else ""
                ),
                pd.Timedelta("1h"),
            )
        if incompatibilities is not None:
            incompatibilities.append(
                "no enabled analysis has a bounded-memory streaming layout"
            )
        return None
    time_columns = {layout[1] for layout in layouts}
    topology_columns = {layout[2] for layout in layouts if layout[2]}
    if plane_efficiency_setting is not None:
        topology_columns.add(plane_efficiency_setting["topology_column"])
    windows = {layout[3] for layout in layouts}
    if len(time_columns) != 1 or len(topology_columns) > 1 or len(windows) != 1:
        if incompatibilities is not None:
            descriptions = ", ".join(
                f"{name}(time={time_column}, "
                f"topology={topology_column or 'unused'}, window={window})"
                for name, time_column, topology_column, window in layouts
            )
            incompatibilities.append(
                "enabled streaming analyses do not share the same layout: "
                + descriptions
            )
        return None
    window = next(iter(windows))
    if int(window.value) % 1_000_000_000:
        if incompatibilities is not None:
            affected = ", ".join(layout[0] for layout in layouts)
            incompatibilities.append(
                f"{affected}: accumulation window {window} is not a whole "
                "number of seconds"
            )
        return None
    return (
        next(iter(time_columns)),
        next(iter(topology_columns), ""),
        window,
    )


def main() -> int:
    args = arguments()
    config = load_configuration(args.config)
    gates = parse_gates(config["gates"])
    topology_setting = derived_topology_setting(config)
    root = STATIONS_ROOT / config["station_name"]
    lake = root / "STAGE_1_PRODUCTS" / "EVENT_DATA" / "PARQUET_LAKE"
    simulation_selection: Mingo00Selection | None = None
    if config["station_name"] == "MINGO00":
        simulation_selection = select_mingo00_products(
            lake,
            config["maximum"],
            config["close_parameters"],
            product_factory=Product,
            parquet_basename=parquet_basename,
            acquisition_time=acquisition_time,
        )
        files = simulation_selection.products
        print(
            f"Found {simulation_selection.candidate_count} MINGO00 products with simulation "
            f"metadata; selected tightest parameter cluster of {len(files)} using: "
            + ", ".join(simulation_selection.close_parameters)
        )
        print(f"Parameter-cluster center: {simulation_selection.center_basename}")
        for index, product in enumerate(files, 1):
            param_id = simulation_selection.param_set_id_by_basename[product.basename]
            distance = simulation_selection.distance_by_basename[product.basename]
            values = simulation_selection.values_by_basename[product.basename]
            print(
                f"  {index}. param_set_id={param_id} distance={distance:.6g} "
                f"{product.basename}  {values}"
            )
    else:
        candidates = discover(lake, config["start"], config["end"])
        files = tightest_block(candidates, config["maximum"])
        print(f"Found {len(candidates)} files in range; selected tightest consecutive block of {len(files)}:")
        for index, product in enumerate(files, 1):
            print(f"  {index}. {product.acquired}  {product.basename}")
        if len(files) > 1:
            print(f"Acquisition-start span: {files[-1].acquired - files[0].acquired}")
    available, types = schemas(files)
    available_set = set(available)
    show_columns(available, types)

    derived_names = derived_column_names() if topology_setting["enabled"] else []
    if derived_names:
        print("Derived columns available to gate conditions:")
        for name in derived_names:
            print(f"  - {name}")
        print()
    gate_columns: set[str] = set()
    for gate in gates:
        gate_columns.update(condition_columns(gate.condition, location=f"gate[{gate.code}]"))
    allowed_columns = available_set | set(derived_names)
    missing_gate_columns = sorted(gate_columns - allowed_columns)
    if missing_gate_columns:
        raise ValueError("Gate condition columns absent from schema: " + ", ".join(missing_gate_columns))
    source_columns = topology_source_columns(topology_setting)
    missing_sources = sorted(set(source_columns) - available_set)
    if missing_sources:
        raise ValueError("Derived strip-topology source columns absent: " + ", ".join(missing_sources))
    rate_setting = time_series_setting(config, available_set)
    burst_setting = one_second_burst_setting(config, available_set)
    efficiency_setting = efficiency_time_series_setting(config, gates, available_set)
    gate_comparison = enabled_gate_comparison_setting(config, available_set, gates)
    frequency_efficiency_correction = environment_frequency_efficiency_setting(config)
    if frequency_efficiency_correction is not None and gate_comparison is None:
        raise ValueError(
            "environment_frequency_efficiency_correction requires "
            "enabled_gate_comparison"
        )
    plane_combination = plane_combination_setting(config, gates, available_set)
    histogram_setting = angular_histogram_setting(config, available_set)
    charge_cluster_setting = charge_cluster_size_study_setting(
        config, available_set, topology_setting,
    )
    plane_xy_setting = plane_xy_histogram_setting(config, available_set)
    plane_efficiency_setting = plane_efficiency_map_setting(
        config, available_set,
    )
    fit_projection_setting = fit_projection_time_series_setting(config, available_set)
    calibration_comparison = charge_calibration_comparison_setting(
        config, available_set,
    )
    charge_scatter_setting = topology_charge_scatter_setting(
        config, gates, available_set,
    )
    y_position_setting = topology_y_position_setting(config, gates, available_set)
    charge_scatter_settings, y_position_settings = expand_topology_diagnostic_settings(
        config, gates, available_set, charge_scatter_setting, y_position_setting,
    )
    needed = list(dict.fromkeys([
        *(column for column in gate_columns if column in available_set),
        *source_columns,
        *([] if rate_setting is None else [rate_setting["column"]]),
        *([] if burst_setting is None else [burst_setting["time_column"]]),
        *([] if efficiency_setting is None else [
            efficiency_setting["time_column"], efficiency_setting["topology_column"],
        ]),
        *([] if gate_comparison is None else [
            gate_comparison["time_column"], gate_comparison["topology_column"],
        ]),
        *([] if plane_combination is None else [
            plane_combination["time_column"], plane_combination["topology_column"],
        ]),
        *([] if histogram_setting is None else [
            *(variable["column"] for variable in histogram_setting["variables"]),
            *(
                variable["sign_by_cosine_column"]
                for variable in histogram_setting["variables"]
                if variable["sign_by_cosine_column"]
            ),
            *histogram_setting["z_columns"],
        ]),
        *(
            []
            if charge_cluster_setting is None
            else charge_cluster_setting["charge_columns"]
        ),
        *([] if plane_xy_setting is None else plane_xy_setting["columns"]),
        *(
            []
            if plane_efficiency_setting is None
            else plane_efficiency_setting["columns"]
        ),
        *([] if fit_projection_setting is None else [
            fit_projection_setting["time_column"],
            fit_projection_setting["x_column"],
            fit_projection_setting["y_column"],
        ]),
        *([] if calibration_comparison is None else calibration_comparison["columns"]),
        *(column for setting in charge_scatter_settings for column in setting["columns"]),
        *(column for setting in y_position_settings for column in setting["columns"]),
    ]))
    streaming_issues: list[str] = []
    stream_layout = streaming_parameters(
        rate_setting, burst_setting, efficiency_setting, gate_comparison,
        plane_combination, histogram_setting, fit_projection_setting,
        calibration_comparison,
        charge_scatter_settings, y_position_settings,
        charge_cluster_setting=charge_cluster_setting,
        plane_xy_setting=plane_xy_setting,
        plane_efficiency_setting=plane_efficiency_setting,
        incompatibilities=streaming_issues,
    )
    aggregates: StreamingGateAggregates | None = None
    frame: pd.DataFrame | None = None
    masks: dict[str, pd.Series] | None = None
    if stream_layout is not None:
        time_column, topology_column, window = stream_layout
        fingerprint = streaming_fingerprint(
            config["config_paths"], files, needed, stream_layout,
        )
        group_name = f"{files[0].basename}_{files[-1].basename}"
        checkpoint_path = (
            root / "STAGE_1_PRODUCTS_TESTS" / OUTPUT_NAME
            / ".STREAMING_CACHE"
            / f"{group_name}_{fingerprint[:16]}.pickle"
        )
        print(
            "\nUsing bounded-memory streaming aggregation: "
            f"time={time_column}, topology={topology_column or 'unused'}, "
            f"window={window}, batch_rows=100,000\n"
            f"Checkpoint: {checkpoint_path}"
        )
        aggregates = stream_events(
            files, needed, gates, topology_setting,
            time_column=time_column,
            topology_column=topology_column,
            window=window,
            angular_histogram_setting=histogram_setting,
            charge_cluster_setting=charge_cluster_setting,
            plane_xy_setting=plane_xy_setting,
            plane_efficiency_setting=plane_efficiency_setting,
            checkpoint_path=checkpoint_path,
            fingerprint=fingerprint,
        )
    else:
        issue_lines = "\n".join(
            f"  - {issue}" for issue in streaming_issues
        )
        print(
            "\nUsing event-level compatibility mode because the following enabled "
            "analysis configuration cannot be reduced to the shared streaming "
            f"layout:\n{issue_lines}"
        )
        frame = read_events(files, needed)
        add_derived_topology_columns(frame, topology_setting)
        masks = assign_gates(frame, gates)

    interval = (
        "PARAMETER_CLOSE"
        if simulation_selection is not None
        else f"{config['start']:%Y%m%d_%H%M%S}_{config['end']:%Y%m%d_%H%M%S}"
    )
    group = f"{files[0].basename}_{files[-1].basename}"
    output = root / "STAGE_1_PRODUCTS_TESTS" / OUTPUT_NAME / f"{interval}_{group}"
    rate_dir = output / "RATE_TIMESERIES"
    burst_dir = output / "ONE_SECOND_BURST_DIAGNOSTICS"
    efficiency_dir = output / "EFFICIENCY_TIMESERIES"
    gate_comparison_dir = output / "ENABLED_GATE_COMPARISON"
    frequency_efficiency_dir = (
        output / "ENVIRONMENT_FREQUENCY_EFFICIENCY_CORRECTION"
    )
    plane_combination_dir = output / "PLANE_COMBINATIONS"
    angular_dir = output / "ANGULAR_HISTOGRAMS"
    charge_cluster_dir = output / "CHARGE_CLUSTER_SIZE_STUDY"
    plane_xy_dir = output / "PLANE_XY_HISTOGRAMS"
    plane_efficiency_dir = output / "EFFICIENCY_PLANE"
    fit_projection_dir = output / "FIT_PROJECTION_TIME_SERIES"
    charge_calibration_dir = output / "CHARGE_CALIBRATION_COMPARISON"
    scatter_dir = output / "SCATTERS"
    for directory in (
        output, rate_dir, burst_dir, efficiency_dir, gate_comparison_dir,
        frequency_efficiency_dir, plane_combination_dir, angular_dir,
        charge_cluster_dir, plane_xy_dir, fit_projection_dir,
        plane_efficiency_dir, charge_calibration_dir, scatter_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    for directory in (
        rate_dir, burst_dir, efficiency_dir, gate_comparison_dir,
        frequency_efficiency_dir, plane_combination_dir, angular_dir,
        charge_cluster_dir, plane_xy_dir, fit_projection_dir,
        plane_efficiency_dir, charge_calibration_dir, scatter_dir,
    ):
        for pattern in ("*.png", "*.csv"):
            for obsolete in directory.glob(pattern):
                obsolete.unlink()

    manifest_path = output / "selected_files.csv"
    pd.DataFrame([
        {
            "selection_order": index,
            "station": config["station_name"],
            "filename_base": product.basename,
            "acquisition_datetime": product.acquired,
            "rows": pq.ParquetFile(product.path).metadata.num_rows,
            "path": str(product.path),
            **(
                simulation_selection.manifest_fields(product.basename)
                if simulation_selection is not None
                else {"selection_mode": "chronological_minimum_span"}
            ),
        }
        for index, product in enumerate(files, 1)
    ]).to_csv(manifest_path, index=False)
    summary_path = output / "gate_summary.csv"
    if aggregates is not None:
        summary = gate_summary_frame(aggregates, gates)
        summary.to_csv(summary_path, index=False)
    else:
        assert frame is not None and masks is not None
        summary = write_gate_summary(frame, gates, masks, summary_path)
    print("\nGate population summary:")
    print(summary.to_string(index=False))

    if simulation_selection is not None:
        title = (
            f"{root.name} | {len(files)} simulation-parameter-close files | "
            f"center={simulation_selection.center_basename} | "
            "parameters=" + ",".join(simulation_selection.close_parameters)
        )
    else:
        title = (
            f"{root.name} | {len(files)} consecutive files | "
            f"{files[0].acquired:%Y-%m-%d %H:%M:%S} to "
            f"{files[-1].acquired:%Y-%m-%d %H:%M:%S}"
        )
    selected_start = min(product.acquired for product in files)
    selected_end = max(product.acquired for product in files)
    calibration_paths = generate_calibration_context(
        root,
        selected_start if simulation_selection is not None else config["start"],
        selected_end if simulation_selection is not None else config["end"],
        output / "00_CALIBRATION_CONTEXT",
        title,
        {product.basename for product in files},
        context=config.get("context", "full"),
    )
    environment_paths = generate_environment_context(
        root,
        selected_start,
        selected_end,
        output / "00_ENVIRONMENT_CONTEXT",
        title,
        context_fraction=float(config.get("environment_context_fraction", 0.10)),
        gas_gap_mm=float(config.get("environment_gas_gap_mm", 1.0)),
    )
    calibration_paths.extend(
        generate_calibration_temperature_plots(
            calibration_paths[0],
            environment_paths[0],
            output / "00_CALIBRATION_CONTEXT",
            title,
            {product.basename for product in files},
        )
    )
    rate_csv: Path | None = None
    rate_plots = 0
    if rate_setting is not None:
        if aggregates is not None:
            rate_csv, rate_plots = write_streamed_gate_time_series(
                aggregates, gates, rate_setting, rate_dir, title,
            )
        else:
            assert frame is not None and masks is not None
            rate_csv, rate_plots = write_gate_time_series(
                frame, gates, masks, rate_setting, rate_dir, title,
            )
    burst_csv: Path | None = None
    burst_plots = 0
    if burst_setting is not None:
        assert frame is not None and masks is not None
        burst_csv, burst_plots = write_one_second_burst_diagnostics(
            frame, gates, masks, burst_setting, burst_dir, title,
        )
    efficiency_csv: Path | None = None
    efficiency_plots = 0
    if efficiency_setting is not None:
        if aggregates is not None:
            efficiency_csv, efficiency_plots = (
                write_streamed_efficiency_time_series(
                    aggregates, gates, efficiency_setting, efficiency_dir, title,
                )
            )
        else:
            assert frame is not None and masks is not None
            efficiency_csv, efficiency_plots = write_efficiency_time_series(
                frame, gates, masks, efficiency_setting, efficiency_dir, title,
            )
    gate_efficiency_plot: Path | None = None
    gate_metrics_plot: Path | None = None
    gate_normalized_plot: Path | None = None
    gate_ratio_plot: Path | None = None
    gate_comparison_csv: Path | None = None
    gate_comparison_plots = 0
    if gate_comparison is not None:
        if aggregates is not None:
            comparison_result = write_streamed_enabled_gate_comparison(
                aggregates, gates, gate_comparison, gate_comparison_dir, title,
                environment_paths[0],
            )
        else:
            assert frame is not None and masks is not None
            comparison_result = write_enabled_gate_comparison(
                frame, gates, masks, gate_comparison, gate_comparison_dir, title,
                environment_paths[0],
            )
        (
            gate_efficiency_plot,
            gate_metrics_plot,
            gate_normalized_plot,
            gate_ratio_plot,
            gate_comparison_csv,
            gate_comparison_plots,
        ) = comparison_result
    frequency_efficiency_plots: list[Path] = []
    frequency_efficiency_csvs: list[Path] = []
    frequency_efficiency_plot_count = 0
    if frequency_efficiency_correction is not None:
        if gate_comparison_csv is None:
            raise RuntimeError("Enabled-gate comparison CSV was not produced")
        (
            frequency_efficiency_plots,
            frequency_efficiency_csvs,
            frequency_efficiency_plot_count,
        ) = write_environment_frequency_efficiency_correction(
            gate_comparison_csv, environment_paths[0],
            frequency_efficiency_correction, frequency_efficiency_dir, title,
            gate_comparison["window"],
        )
    plane_combination_plot: Path | None = None
    plane_combination_csv: Path | None = None
    plane_combination_plots = 0
    if plane_combination is not None:
        assert frame is not None and masks is not None
        plane_combination_plot, plane_combination_csv, plane_combination_plots = (
            write_plane_combination_timeseries(
                frame, gates, masks, plane_combination, plane_combination_dir, title,
            )
        )
    angular_csvs: list[Path] = []
    angular_plots = 0
    if histogram_setting is not None:
        if aggregates is not None:
            if aggregates.angular_histograms is None:
                raise RuntimeError("Streaming angular histogram reductions are missing")
            angular_csvs, angular_plots = write_streamed_angular_histograms(
                aggregates.angular_histograms, gates, histogram_setting,
                angular_dir, title,
            )
        else:
            assert frame is not None and masks is not None
            angular_csvs, angular_plots = write_angular_histograms(
                frame, gates, masks, histogram_setting, angular_dir, title,
            )
    charge_cluster_outputs: list[tuple[Path, Path]] = []
    if charge_cluster_setting is not None:
        if aggregates is not None:
            charge_cluster_histograms = aggregates.charge_cluster_histograms
            if charge_cluster_histograms is None:
                raise RuntimeError(
                    "Streaming charge cluster-size reductions are missing"
                )
        else:
            assert frame is not None
            charge_cluster_histograms = StreamingChargeClusterHistograms(
                np.linspace(
                    charge_cluster_setting["x_range"][0],
                    charge_cluster_setting["x_range"][1],
                    charge_cluster_setting["bins"] + 1,
                )
            )
            assert masks is not None
            charge_cluster_histograms.accumulate(frame, masks)
        charge_cluster_outputs = write_charge_cluster_size_study(
            charge_cluster_histograms, gates, charge_cluster_dir, title,
        )
    plane_xy_outputs: list[tuple[Path, Path]] = []
    if plane_xy_setting is not None:
        if aggregates is not None:
            plane_xy_histograms = aggregates.plane_xy_histograms
            if plane_xy_histograms is None:
                raise RuntimeError("Streaming plane X/Y reductions are missing")
        else:
            assert frame is not None and masks is not None
            plane_xy_histograms = StreamingPlaneXYHistograms(
                plane_xy_setting,
                np.linspace(
                    plane_xy_setting["x_range"][0],
                    plane_xy_setting["x_range"][1],
                    plane_xy_setting["bins"] + 1,
                ),
                np.linspace(
                    plane_xy_setting["y_range"][0],
                    plane_xy_setting["y_range"][1],
                    plane_xy_setting["bins"] + 1,
                ),
            )
            plane_xy_histograms.accumulate(frame, masks)
        plane_xy_outputs = write_plane_xy_histograms(
            plane_xy_histograms, gates, plane_xy_dir, title,
        )
    plane_efficiency_outputs: list[tuple[Path, Path, Path, Path]] = []
    if plane_efficiency_setting is not None:
        if aggregates is not None:
            plane_efficiency_maps = aggregates.plane_efficiency_maps
            if plane_efficiency_maps is None:
                raise RuntimeError(
                    "Streaming plane-efficiency reductions are missing"
                )
        else:
            assert frame is not None and masks is not None
            plane_efficiency_maps = StreamingPlaneEfficiencyMaps(
                plane_efficiency_setting,
                np.linspace(
                    plane_efficiency_setting["x_range"][0],
                    plane_efficiency_setting["x_range"][1],
                    plane_efficiency_setting["bins"] + 1,
                ),
                np.linspace(
                    plane_efficiency_setting["y_range"][0],
                    plane_efficiency_setting["y_range"][1],
                    plane_efficiency_setting["bins"] + 1,
                ),
            )
            topology_numeric = pd.to_numeric(
                frame[plane_efficiency_setting["topology_column"]],
                errors="coerce",
            )
            topologies = (
                topology_numeric.where(topology_numeric.mod(1).eq(0))
                .astype("Int64")
                .astype("string")
            )
            plane_efficiency_maps.accumulate(frame, topologies, masks)
        plane_efficiency_outputs = write_plane_efficiency_maps(
            plane_efficiency_maps, gates, plane_efficiency_dir, title,
        )
    fit_projection_csv: Path | None = None
    fit_projection_plots = 0
    if fit_projection_setting is not None:
        assert frame is not None and masks is not None
        fit_projection_csv, fit_projection_plots = write_fit_projection_time_series(
            frame, gates, masks, fit_projection_setting, fit_projection_dir, title,
        )
    charge_calibration_plot: Path | None = None
    charge_calibration_values = 0
    if calibration_comparison is not None:
        assert frame is not None
        charge_calibration_plot, charge_calibration_values = (
            write_charge_calibration_comparison(
                frame, calibration_comparison, charge_calibration_dir, title,
            )
        )
    if charge_scatter_settings or y_position_settings:
        assert frame is not None and masks is not None
    charge_scatter_results = [
        write_topology_charge_scatter(
            frame, files, masks, setting, scatter_dir, title,
        )
        for setting in charge_scatter_settings
    ]
    charge_scatter_plots = sum(result[2] for result in charge_scatter_results)
    y_position_results = [
        write_topology_y_position(
            frame, files, masks, setting, scatter_dir, title,
        )
        for setting in y_position_settings
    ]
    y_position_plots = sum(result[3] for result in y_position_results)
    event_rows = aggregates.total_events if aggregates is not None else len(frame)
    mode = "streamed" if aggregates is not None else "joined"
    print(f"\nProcessed {event_rows:,} event rows ({mode} mode)")
    print(
        f"Wrote {len(calibration_paths) - 1} calibration context plot(s), "
        f"{len(environment_paths) - 1} environment context plot(s), "
        f"{rate_plots} gate-rate plot(s), {efficiency_plots} efficiency plot(s), "
        f"{burst_plots} one-second burst plot(s), "
        f"{gate_comparison_plots} enabled-gate comparison plot(s), "
        f"{frequency_efficiency_plot_count} environment-frequency efficiency "
        "correction plot(s), "
        f"{plane_combination_plots} plane-combination plot(s), "
        f"{angular_plots} angular histogram(s), "
        f"{len(charge_cluster_outputs)} charge cluster-size study plot(s), "
        f"{len(plane_xy_outputs)} plane X/Y histogram plot(s), "
        f"{3 * len(plane_efficiency_outputs)} plane-efficiency map plot(s), "
        f"{fit_projection_plots} fit-projection time-series plot(s), "
        f"{int(charge_calibration_plot is not None)} charge-calibration comparison "
        f"plot(s) from {charge_calibration_values:,} plane events, "
        f"{charge_scatter_plots} topology-charge scatter plot(s), and "
        f"{y_position_plots} topology-Y plot(s)"
    )
    print(f"Selected-file manifest: {manifest_path}")
    print(f"Gate summary: {summary_path}")
    if rate_csv is not None:
        print(f"Gate rate data: {rate_csv}")
    if burst_csv is not None:
        print(f"One-second burst summary: {burst_csv}")
    if efficiency_csv is not None:
        print(f"Efficiency time-series data: {efficiency_csv}")
    if gate_efficiency_plot is not None:
        print(f"Enabled-gate efficiency overlay: {gate_efficiency_plot}")
    if gate_metrics_plot is not None:
        print(f"Enabled-gate rate/efficiency comparison: {gate_metrics_plot}")
    if gate_normalized_plot is not None:
        print(f"Enabled-gate corrected-rate/environment comparison: {gate_normalized_plot}")
    if gate_ratio_plot is not None:
        print(f"Enabled-gate corrected-to-ALL ratio: {gate_ratio_plot}")
    if gate_comparison_csv is not None:
        print(f"Enabled-gate comparison data: {gate_comparison_csv}")
    for plot_path in frequency_efficiency_plots:
        print(f"Environment-frequency efficiency correction: {plot_path}")
    for csv_path in frequency_efficiency_csvs:
        print(f"Environment-frequency efficiency data: {csv_path}")
    if plane_combination_plot is not None:
        print(f"Plane-combination plot: {plane_combination_plot}")
    if plane_combination_csv is not None:
        print(f"Plane-combination data: {plane_combination_csv}")
    for angular_csv in angular_csvs:
        print(f"Angular histogram data: {angular_csv}")
    for charge_cluster_plot, charge_cluster_csv in charge_cluster_outputs:
        print(f"Charge cluster-size study: {charge_cluster_plot}")
        print(f"Charge cluster-size data: {charge_cluster_csv}")
    for plane_xy_plot, plane_xy_csv in plane_xy_outputs:
        print(f"Plane X/Y histogram: {plane_xy_plot}")
        print(f"Plane X/Y histogram data: {plane_xy_csv}")
    for detected_path, missing_path, efficiency_path, csv_path in (
        plane_efficiency_outputs
    ):
        print(f"Plane-efficiency 1234 positions: {detected_path}")
        print(f"Plane-efficiency missing positions: {missing_path}")
        print(f"Plane-efficiency map: {efficiency_path}")
        print(f"Plane-efficiency data: {csv_path}")
    if fit_projection_csv is not None:
        print(f"Fit-projection time-series data: {fit_projection_csv}")
    if charge_calibration_plot is not None:
        print(f"Charge-calibration comparison: {charge_calibration_plot}")
    for plot_path, csv_path, plotted in charge_scatter_results:
        if plotted:
            print(f"Topology charge scatter: {plot_path}")
        print(f"Topology charge scatter summary: {csv_path}")
    for position_path, charge_path, csv_path, _ in y_position_results:
        print(f"Topology Y-position plot: {position_path}")
        print(f"Topology Y/charge plot: {charge_path}")
        print(f"Topology Y/charge data: {csv_path}")
    print(f"Outputs: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
