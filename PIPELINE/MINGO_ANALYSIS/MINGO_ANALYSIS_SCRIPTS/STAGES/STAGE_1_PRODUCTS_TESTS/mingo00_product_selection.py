"""Simulation-parameter selection for MINGO00 Stage-1 product tests."""

from __future__ import annotations

import ast
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np
import pandas as pd


SIMULATION_PARAMETER_COLUMNS = (
    "cos_n",
    "flux_cm2_min",
    "z_plane_1",
    "z_plane_2",
    "z_plane_3",
    "z_plane_4",
    "efficiencies",
    "trigger_combinations",
)
NUMERIC_SCALAR_PARAMETERS = frozenset(
    {
        "cos_n",
        "flux_cm2_min",
        "z_plane_1",
        "z_plane_2",
        "z_plane_3",
        "z_plane_4",
    }
)
NUMERIC_VECTOR_PARAMETERS = frozenset({"efficiencies"})
CATEGORICAL_SET_PARAMETERS = frozenset({"trigger_combinations"})
DEFAULT_SIMULATION_PARAMS = (
    Path(__file__).resolve().parents[4]
    / "MINGO_DIGITAL_TWIN"
    / "SIMULATION_OUTPUTS"
    / "SIMULATED_DATA"
    / "step_final_simulation_params.csv"
)
MAX_EXACT_ANCHORS = 2000


@dataclass(frozen=True)
class Mingo00Selection:
    products: list[Any]
    candidate_count: int
    close_parameters: tuple[str, ...]
    center_basename: str
    distance_by_basename: dict[str, float]
    param_set_id_by_basename: dict[str, int]
    values_by_basename: dict[str, dict[str, Any]]

    def manifest_fields(self, basename: str) -> dict[str, Any]:
        values = self.values_by_basename[basename]
        fields: dict[str, Any] = {
            "selection_mode": "mingo00_parameter_closeness",
            "simulation_param_set_id": self.param_set_id_by_basename[basename],
            "parameter_distance_to_center": self.distance_by_basename[basename],
            "parameter_cluster_center": self.center_basename,
            "mingo00_close_parameters": json.dumps(self.close_parameters),
        }
        for name in self.close_parameters:
            value = values[name]
            fields[f"simulation_{name}"] = (
                json.dumps(value, separators=(",", ":"))
                if isinstance(value, (list, tuple, dict))
                else value
            )
        return fields


def validate_close_parameters(raw: Any) -> tuple[str, ...]:
    if not isinstance(raw, list) or not raw:
        raise ValueError(
            "MINGO00 requires a nonempty mingo00_close_parameters YAML list"
        )
    parameters = tuple(str(value).strip() for value in raw)
    if any(not value for value in parameters):
        raise ValueError("mingo00_close_parameters cannot contain empty names")
    if len(set(parameters)) != len(parameters):
        raise ValueError("mingo00_close_parameters cannot contain duplicates")
    unknown = [name for name in parameters if name not in SIMULATION_PARAMETER_COLUMNS]
    if unknown:
        raise ValueError(
            "Unknown MINGO00 closeness parameter(s): "
            + ", ".join(unknown)
            + ". Supported: "
            + ", ".join(SIMULATION_PARAMETER_COLUMNS)
        )
    return parameters


def _structured_value(value: Any, *, parameter: str) -> list[Any]:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (list, tuple)):
        return list(value)
    if pd.isna(value):
        raise ValueError(f"Missing simulation parameter {parameter}")
    text = str(value).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        try:
            parsed = ast.literal_eval(text)
        except (SyntaxError, ValueError) as exc:
            raise ValueError(
                f"Cannot parse structured simulation parameter {parameter}: {value!r}"
            ) from exc
    if not isinstance(parsed, (list, tuple)):
        raise ValueError(f"Simulation parameter {parameter} must contain a list")
    return list(parsed)


def _prepare_parameter_values(
    frame: pd.DataFrame,
    parameters: Sequence[str],
) -> tuple[dict[str, Any], dict[str, list[Any]]]:
    prepared: dict[str, Any] = {}
    serializable: dict[str, list[Any]] = {}
    for name in parameters:
        if name in NUMERIC_SCALAR_PARAMETERS:
            values = pd.to_numeric(frame[name], errors="coerce").to_numpy(dtype=float)
            if not np.isfinite(values).all():
                raise ValueError(f"Simulation parameter {name} contains missing/nonfinite values")
            span = float(np.max(values) - np.min(values))
            prepared[name] = (values, span)
            serializable[name] = values.tolist()
        elif name in NUMERIC_VECTOR_PARAMETERS:
            rows = [_structured_value(value, parameter=name) for value in frame[name]]
            lengths = {len(row) for row in rows}
            if len(lengths) != 1 or not lengths or next(iter(lengths)) == 0:
                raise ValueError(f"Simulation parameter {name} has inconsistent/empty vectors")
            matrix = np.asarray(rows, dtype=float)
            if not np.isfinite(matrix).all():
                raise ValueError(f"Simulation parameter {name} contains missing/nonfinite values")
            spans = np.ptp(matrix, axis=0)
            prepared[name] = (matrix, spans)
            serializable[name] = matrix.tolist()
        elif name in CATEGORICAL_SET_PARAMETERS:
            rows = [
                tuple(sorted({str(item).strip() for item in _structured_value(value, parameter=name)}))
                for value in frame[name]
            ]
            prepared[name] = rows
            serializable[name] = [list(row) for row in rows]
        else:  # validate_close_parameters makes this unreachable.
            raise ValueError(f"Unsupported simulation parameter: {name}")
    return prepared, serializable


def _distance_from(
    index: int,
    prepared: dict[str, Any],
    parameters: Sequence[str],
    size: int,
) -> np.ndarray:
    distance = np.zeros(size, dtype=float)
    for name in parameters:
        values = prepared[name]
        if name in NUMERIC_SCALAR_PARAMETERS:
            vector, span = values
            if span > 0:
                distance += np.abs(vector - vector[index]) / span
        elif name in NUMERIC_VECTOR_PARAMETERS:
            matrix, spans = values
            active = spans > 0
            if bool(active.any()):
                distance += np.mean(
                    np.abs(matrix[:, active] - matrix[index, active]) / spans[active],
                    axis=1,
                )
        elif name in CATEGORICAL_SET_PARAMETERS:
            reference = set(values[index])
            categorical_distance = np.empty(size, dtype=float)
            for other_index, raw_other in enumerate(values):
                other = set(raw_other)
                union = reference | other
                categorical_distance[other_index] = (
                    0.0 if not union else 1.0 - len(reference & other) / len(union)
                )
            distance += categorical_distance
    return distance / float(len(parameters))


def _anchor_indices(size: int) -> np.ndarray:
    if size <= MAX_EXACT_ANCHORS:
        return np.arange(size, dtype=int)
    return np.unique(
        np.linspace(0, size - 1, num=MAX_EXACT_ANCHORS, dtype=int)
    )


def select_mingo00_products(
    lake: Path,
    maximum: int,
    close_parameters: Sequence[str],
    *,
    product_factory: Callable[[Path, str, Any], Any],
    parquet_basename: Callable[[Path], str | None],
    acquisition_time: Callable[[str], Any],
    params_path: Path = DEFAULT_SIMULATION_PARAMS,
) -> Mingo00Selection:
    parameters = validate_close_parameters(list(close_parameters))
    if maximum < 1:
        raise ValueError("max_datafiles must be at least 1")
    if not lake.is_dir():
        raise FileNotFoundError(f"Parquet lake not found: {lake}")
    if not params_path.is_file():
        raise FileNotFoundError(f"Simulation parameter metadata not found: {params_path}")

    product_paths: dict[str, Path] = {}
    for path in sorted(lake.glob("*.parquet")):
        basename = parquet_basename(path)
        if basename is not None:
            product_paths[basename] = path
    if not product_paths:
        raise ValueError(f"No MINGO00 parquet products found in {lake}")

    required = ["file_name", "param_set_id", "execution_time", *parameters]
    header = pd.read_csv(params_path, nrows=0).columns.tolist()
    missing_columns = [name for name in required if name not in header]
    if missing_columns:
        raise ValueError(
            "Simulation parameter metadata is missing: " + ", ".join(missing_columns)
        )
    frame = pd.read_csv(params_path, usecols=required, low_memory=False)
    frame["basename"] = frame["file_name"].astype(str).map(
        lambda value: Path(value.strip()).stem
    )
    frame = frame.loc[frame["basename"].isin(product_paths)].copy()
    if frame.empty:
        raise ValueError(
            "None of the MINGO00 parquet products occur in "
            f"{params_path}"
        )

    frame["_execution"] = pd.to_datetime(frame["execution_time"], errors="coerce", utc=True)
    frame = frame.sort_values(
        ["basename", "_execution", "param_set_id"], na_position="first"
    ).drop_duplicates("basename", keep="last")
    absent = sorted(set(product_paths) - set(frame["basename"]))
    if absent:
        print(
            "Warning: ignored MINGO00 product(s) without simulation parameters: "
            + ", ".join(absent)
        )
    frame["param_set_id"] = pd.to_numeric(frame["param_set_id"], errors="raise").astype(int)
    frame = frame.sort_values(["param_set_id", "basename"]).reset_index(drop=True)

    prepared, serializable = _prepare_parameter_values(frame, parameters)
    size = len(frame)
    count = min(maximum, size)
    basename_values = frame["basename"].astype(str).tolist()
    param_ids = frame["param_set_id"].to_numpy(dtype=int)
    basename_rank = np.asarray(basename_values, dtype=object)

    best: tuple[tuple[Any, ...], int, np.ndarray, np.ndarray] | None = None
    for anchor in _anchor_indices(size):
        distances = _distance_from(anchor, prepared, parameters, size)
        order = np.lexsort((basename_rank, param_ids, distances))
        chosen = order[:count]
        chosen_distances = distances[chosen]
        score = (
            float(np.max(chosen_distances)),
            float(np.mean(chosen_distances)),
            int(param_ids[anchor]),
            basename_values[anchor],
        )
        if best is None or score < best[0]:
            best = (score, int(anchor), chosen, distances)
    if best is None:
        raise RuntimeError("Unable to select a MINGO00 parameter cluster")

    _, center_index, chosen_indices, all_distances = best
    chosen_indices = np.asarray(
        sorted(chosen_indices.tolist(), key=lambda idx: (param_ids[idx], basename_values[idx])),
        dtype=int,
    )
    products = [
        product_factory(
            product_paths[basename_values[index]],
            basename_values[index],
            acquisition_time(basename_values[index]),
        )
        for index in chosen_indices
    ]
    distance_by_basename = {
        basename_values[index]: float(all_distances[index]) for index in chosen_indices
    }
    param_set_id_by_basename = {
        basename_values[index]: int(param_ids[index]) for index in chosen_indices
    }
    values_by_basename: dict[str, dict[str, Any]] = {}
    for index in chosen_indices:
        values_by_basename[basename_values[index]] = {
            name: serializable[name][index] for name in parameters
        }
    return Mingo00Selection(
        products=products,
        candidate_count=size,
        close_parameters=parameters,
        center_basename=basename_values[center_index],
        distance_by_basename=distance_by_basename,
        param_set_id_by_basename=param_set_id_by_basename,
        values_by_basename=values_by_basename,
    )
