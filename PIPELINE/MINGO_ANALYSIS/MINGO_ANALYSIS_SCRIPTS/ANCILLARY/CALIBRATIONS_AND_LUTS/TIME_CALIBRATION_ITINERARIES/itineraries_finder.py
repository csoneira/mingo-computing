#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY/CALIBRATIONS_AND_LUTS/TIME_CALIBRATION_ITINERARIES/itineraries_finder.py
Purpose: Deterministic generation and validation of time-calibration itineraries.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-05
Runtime: python3
Usage: python3 PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY/CALIBRATIONS_AND_LUTS/TIME_CALIBRATION_ITINERARIES/itineraries_finder.py [options]
Inputs: Existing itineraries and generation parameters.
Outputs: A validated `itineraries.csv` file and an example side-view itinerary plot.
Notes: Keeps behavior reproducible with explicit random seed and graph validation.
"""

from __future__ import annotations

import argparse
import random
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Set, Tuple

import yaml

NODE_PATTERN = re.compile(r"^P([1-4])s([1-4])$")
NODES: Tuple[str, ...] = tuple(
    f"P{plane}s{strip}"
    for plane in range(1, 5)
    for strip in range(1, 5)
)
NODE_SET: Set[str] = set(NODES)
ITINERARY_FILE_PATH = Path(__file__).resolve().parent / "itineraries.csv"
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "itineraries_finder.config.yaml"
DEFAULT_EXAMPLE_PLOT_PATH = Path(__file__).resolve().parent / "itinerary_example_side_view.png"

PLANE_PAIR_ORDER: Tuple[Tuple[int, int], ...] = (
    (1, 3),
    (1, 4),
    (2, 4),
    (3, 4),
    (1, 2),
    (2, 3),
)
STRIP_PAIR_PATTERNS: Tuple[Tuple[int, int], ...] = (
    (1, 1),
    (2, 2),
    (3, 3),
    (4, 4),
    (1, 2),
    (2, 1),
    (2, 3),
    (3, 2),
    (3, 4),
    (4, 3),
    (1, 3),
    (3, 1),
    (2, 4),
    (4, 2),
    (1, 4),
)

DEFAULT_NUM_ITINERARIES = 256
DEFAULT_CANDIDATE_POOL = 12000
DEFAULT_MAX_ATTEMPTS = 500000
DEFAULT_POSITION_WEIGHT = 6.0
DEFAULT_COLORMAP_MAX = 0.88

Edge = Tuple[str, str]
PathTuple = Tuple[str, ...]


@dataclass(frozen=True)
class QualitySummary:
    itinerary_count: int
    edge_count_used: int
    edge_count_total: int
    edge_frequency_min: int
    edge_frequency_max: int
    edge_frequency_mean: float
    edge_frequency_std: float
    position_gap_max: int
    position_gap_mean: float


@dataclass(frozen=True)
class SelectionUnit:
    key: PathTuple
    paths: Tuple[PathTuple, ...]
    edge_increments: Tuple[Tuple[Edge, int], ...]
    position_increments: Tuple[Tuple[Tuple[str, int], int], ...]


def canonical_edge(node_a: str, node_b: str) -> Edge:
    return (node_a, node_b) if node_a < node_b else (node_b, node_a)


def canonical_path(path: Sequence[str]) -> PathTuple:
    path_tuple = tuple(path)
    reverse_tuple = tuple(reversed(path_tuple))
    return path_tuple if path_tuple <= reverse_tuple else reverse_tuple


def itinerary_edges(itinerary: Sequence[str]) -> List[Edge]:
    return [
        canonical_edge(previous_node, next_node)
        for previous_node, next_node in zip(itinerary, itinerary[1:])
    ]


def load_itineraries_from_file(file_path: Path, required: bool = True) -> List[PathTuple]:
    if not file_path.exists():
        if required:
            raise FileNotFoundError(f"Cannot find itineraries file: {file_path}")
        return []

    itineraries: List[PathTuple] = []
    with file_path.open("r", encoding="utf-8") as itinerary_file:
        for line_number, raw_line in enumerate(itinerary_file, start=1):
            stripped_line = raw_line.strip()
            if not stripped_line or stripped_line.startswith("#"):
                continue
            segments = tuple(
                segment.strip()
                for segment in stripped_line.split(",")
                if segment.strip()
            )
            if not segments:
                continue
            for node_name in segments:
                if NODE_PATTERN.match(node_name) is None:
                    raise ValueError(
                        f"{file_path}:{line_number} contains invalid node {node_name!r}."
                    )
            itineraries.append(segments)

    if not itineraries and required:
        raise ValueError(f"Itineraries file {file_path} is empty.")
    return itineraries


def write_itineraries_to_file(file_path: Path, itineraries: Iterable[Sequence[str]]) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    unique_itineraries: Dict[PathTuple, None] = {}

    for itinerary in itineraries:
        itinerary_tuple = tuple(itinerary)
        if itinerary_tuple:
            unique_itineraries.setdefault(itinerary_tuple, None)

    with file_path.open("w", encoding="utf-8") as itinerary_file:
        for itinerary_tuple in unique_itineraries:
            itinerary_file.write(",".join(itinerary_tuple) + "\n")


def structural_edge_set() -> Set[Edge]:
    edges: Set[Edge] = set()
    for plane_a, plane_b in PLANE_PAIR_ORDER:
        for strip_a, strip_b in STRIP_PAIR_PATTERNS:
            node_a = f"P{plane_a}s{strip_a}"
            node_b = f"P{plane_b}s{strip_b}"
            edges.add(canonical_edge(node_a, node_b))
    return edges


def edge_set_from_itineraries(itineraries: Iterable[Sequence[str]]) -> Set[Edge]:
    edges: Set[Edge] = set()
    for itinerary in itineraries:
        edges.update(itinerary_edges(itinerary))
    return edges


def validate_itinerary(itinerary: Sequence[str], allowed_edges: Set[Edge]) -> Tuple[bool, str]:
    if len(itinerary) != len(NODES):
        return False, f"Expected {len(NODES)} nodes, got {len(itinerary)}."
    if len(set(itinerary)) != len(NODES):
        return False, "Itinerary contains duplicated nodes."
    if set(itinerary) != NODE_SET:
        missing = sorted(NODE_SET - set(itinerary))
        extra = sorted(set(itinerary) - NODE_SET)
        return False, f"Node mismatch. Missing={missing}, Extra={extra}"
    for edge in itinerary_edges(itinerary):
        if edge not in allowed_edges:
            return False, f"Invalid edge transition: {edge[0]}->{edge[1]}"
    return True, ""


def validate_itineraries(itineraries: Iterable[Sequence[str]], allowed_edges: Set[Edge]) -> None:
    seen: Set[PathTuple] = set()
    for index, itinerary in enumerate(itineraries, start=1):
        itinerary_tuple = tuple(itinerary)
        is_valid, reason = validate_itinerary(itinerary_tuple, allowed_edges)
        if not is_valid:
            raise ValueError(f"Itinerary #{index} is invalid: {reason}")
        if itinerary_tuple in seen:
            raise ValueError(f"Itinerary #{index} is duplicated.")
        seen.add(itinerary_tuple)


def build_adjacency(edges: Set[Edge]) -> Dict[str, Tuple[str, ...]]:
    adjacency: Dict[str, Set[str]] = {node: set() for node in NODES}
    for node_a, node_b in edges:
        adjacency[node_a].add(node_b)
        adjacency[node_b].add(node_a)
    return {
        node: tuple(sorted(neighbors))
        for node, neighbors in adjacency.items()
    }


def assert_graph_connected(adjacency: Dict[str, Tuple[str, ...]]) -> None:
    visited: Set[str] = set()
    pending: List[str] = [NODES[0]]
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        for neighbor in adjacency[current]:
            if neighbor not in visited:
                pending.append(neighbor)

    if visited != NODE_SET:
        missing = sorted(NODE_SET - visited)
        raise RuntimeError(f"Allowed-edge graph is disconnected. Missing nodes: {missing}")


def _forward_degree(
    node: str,
    visited: Set[str],
    adjacency: Dict[str, Tuple[str, ...]],
) -> int:
    return sum(1 for neighbor in adjacency[node] if neighbor not in visited)


def _extend_path(
    path: List[str],
    visited: Set[str],
    adjacency: Dict[str, Tuple[str, ...]],
    rng: random.Random,
) -> bool:
    if len(path) == len(NODES):
        return True

    current = path[-1]
    candidates = [neighbor for neighbor in adjacency[current] if neighbor not in visited]
    if not candidates:
        return False

    rng.shuffle(candidates)
    candidates.sort(
        key=lambda candidate: (
            _forward_degree(candidate, visited, adjacency),
            rng.random(),
        )
    )

    for next_node in candidates:
        visited.add(next_node)
        path.append(next_node)
        if _extend_path(path, visited, adjacency, rng):
            return True
        path.pop()
        visited.remove(next_node)

    return False


def sample_hamiltonian_path(
    adjacency: Dict[str, Tuple[str, ...]],
    rng: random.Random,
) -> PathTuple | None:
    start_nodes = list(NODES)
    rng.shuffle(start_nodes)
    for start_node in start_nodes:
        path = [start_node]
        visited = {start_node}
        if _extend_path(path, visited, adjacency, rng):
            return tuple(path)
    return None


def generate_candidate_paths(
    adjacency: Dict[str, Tuple[str, ...]],
    seed: int,
    target_unique: int,
    max_attempts: int,
    initial_candidates: Sequence[PathTuple] | None = None,
) -> Tuple[List[PathTuple], int]:
    candidates: List[PathTuple] = []
    seen: Set[PathTuple] = set()

    for itinerary in initial_candidates or ():
        itinerary_tuple = tuple(itinerary)
        if itinerary_tuple not in seen:
            seen.add(itinerary_tuple)
            candidates.append(itinerary_tuple)

    attempts = 0
    rng = random.Random(seed)
    while attempts < max_attempts and len(candidates) < target_unique:
        attempts += 1
        path = sample_hamiltonian_path(adjacency, rng)
        if path is None:
            continue
        if path in seen:
            continue
        seen.add(path)
        candidates.append(path)

    return candidates, attempts


def build_selection_units(
    candidates: Sequence[PathTuple],
    reverse_pairs: bool,
) -> List[SelectionUnit]:
    def _build_unit(key: PathTuple, paths: Tuple[PathTuple, ...]) -> SelectionUnit:
        edge_counter = Counter(
            edge
            for path in paths
            for edge in itinerary_edges(path)
        )
        position_counter = Counter(
            (node, index)
            for path in paths
            for index, node in enumerate(path)
        )
        return SelectionUnit(
            key=key,
            paths=paths,
            edge_increments=tuple(sorted(edge_counter.items())),
            position_increments=tuple(sorted(position_counter.items())),
        )

    if reverse_pairs:
        canonical_paths: Set[PathTuple] = {
            canonical_path(path)
            for path in candidates
        }
        units: List[SelectionUnit] = []
        for canonical in sorted(canonical_paths):
            reversed_path = tuple(reversed(canonical))
            paths = (canonical, reversed_path)
            units.append(_build_unit(canonical, paths))
        return units

    unique_candidates = sorted(set(candidates))
    return [
        _build_unit(itinerary, (itinerary,))
        for itinerary in unique_candidates
    ]


def unit_score(
    unit: SelectionUnit,
    edge_counts: Counter[Edge],
    position_counts: Dict[str, Counter[int]],
    edge_target: float,
    position_target: float,
    position_weight: float,
) -> float:
    score = 0.0

    for edge, increment in unit.edge_increments:
        current_count = float(edge_counts[edge])
        updated_count = current_count + float(increment)
        score += ((current_count - edge_target) ** 2) - ((updated_count - edge_target) ** 2)

    for (node, position), increment in unit.position_increments:
        current_count = float(position_counts[node][position])
        updated_count = current_count + float(increment)
        score += position_weight * (
            ((current_count - position_target) ** 2) - ((updated_count - position_target) ** 2)
        )

    return score


def select_itineraries(
    units: Sequence[SelectionUnit],
    num_itineraries: int,
    reverse_pairs: bool,
    edge_universe: Set[Edge],
    position_weight: float,
) -> List[PathTuple]:
    if num_itineraries <= 0:
        raise ValueError("num_itineraries must be > 0.")
    if not edge_universe:
        raise ValueError("edge_universe must not be empty.")

    if reverse_pairs:
        target_unit_count = num_itineraries // 2
        leftover_single = num_itineraries % 2
    else:
        target_unit_count = num_itineraries
        leftover_single = 0

    if target_unit_count > len(units):
        raise RuntimeError(
            f"Not enough candidate units: requested {target_unit_count}, available {len(units)}."
        )

    selected_units: List[SelectionUnit] = []
    remaining_units = set(range(len(units)))
    edge_counts: Counter[Edge] = Counter()
    position_counts: Dict[str, Counter[int]] = {
        node: Counter() for node in NODES
    }
    edge_target = float(num_itineraries * (len(NODES) - 1)) / float(len(edge_universe))
    position_target = float(num_itineraries) / float(len(NODES))

    for _ in range(target_unit_count):
        best_index = None
        best_score = float("-inf")
        best_key: PathTuple | None = None

        for index in remaining_units:
            current_unit = units[index]
            current_score = unit_score(
                current_unit,
                edge_counts,
                position_counts,
                edge_target=edge_target,
                position_target=position_target,
                position_weight=position_weight,
            )
            if (
                current_score > best_score
                or (
                    current_score == best_score
                    and (best_key is None or current_unit.key < best_key)
                )
            ):
                best_score = current_score
                best_index = index
                best_key = current_unit.key

        if best_index is None:
            raise RuntimeError("Selection failed unexpectedly.")

        selected_unit = units[best_index]
        selected_units.append(selected_unit)
        remaining_units.remove(best_index)

        for edge, increment in selected_unit.edge_increments:
            edge_counts[edge] += increment
        for (node, position), increment in selected_unit.position_increments:
            position_counts[node][position] += increment

    selected_itineraries = [
        itinerary
        for selected_unit in selected_units
        for itinerary in selected_unit.paths
    ]

    if leftover_single:
        best_single_path: PathTuple | None = None
        best_single_score = float("-inf")
        for index in remaining_units:
            current_path = units[index].paths[0]
            single_edge_counter = Counter(itinerary_edges(current_path))
            single_position_counter = Counter(
                (node, pos) for pos, node in enumerate(current_path)
            )
            single_unit = SelectionUnit(
                key=current_path,
                paths=(current_path,),
                edge_increments=tuple(sorted(single_edge_counter.items())),
                position_increments=tuple(sorted(single_position_counter.items())),
            )
            current_score = unit_score(
                single_unit,
                edge_counts,
                position_counts,
                edge_target=edge_target,
                position_target=position_target,
                position_weight=position_weight,
            )
            if (
                current_score > best_single_score
                or (
                    current_score == best_single_score
                    and (
                        best_single_path is None
                        or current_path < best_single_path
                    )
                )
            ):
                best_single_score = current_score
                best_single_path = current_path

        if best_single_path is None:
            raise RuntimeError("Unable to select odd leftover itinerary.")
        selected_itineraries.append(best_single_path)

    return selected_itineraries


def summarize_quality(
    itineraries: Sequence[Sequence[str]],
    allowed_edges: Set[Edge],
) -> QualitySummary:
    if not itineraries:
        return QualitySummary(
            itinerary_count=0,
            edge_count_used=0,
            edge_count_total=len(allowed_edges),
            edge_frequency_min=0,
            edge_frequency_max=0,
            edge_frequency_mean=0.0,
            edge_frequency_std=0.0,
            position_gap_max=0,
            position_gap_mean=0.0,
        )

    edge_counts: Counter[Edge] = Counter()
    position_counts: Dict[str, List[int]] = {
        node: [0] * len(NODES)
        for node in NODES
    }

    for itinerary in itineraries:
        for edge in itinerary_edges(itinerary):
            edge_counts[edge] += 1
        for position, node in enumerate(itinerary):
            position_counts[node][position] += 1

    edge_freq_values = list(edge_counts.values())
    edge_frequency_mean = sum(edge_freq_values) / float(len(edge_freq_values))
    edge_frequency_std = (
        sum((value - edge_frequency_mean) ** 2 for value in edge_freq_values)
        / float(len(edge_freq_values))
    ) ** 0.5

    position_gaps = [
        max(counts) - min(counts)
        for counts in position_counts.values()
    ]

    return QualitySummary(
        itinerary_count=len(itineraries),
        edge_count_used=len(edge_counts),
        edge_count_total=len(allowed_edges),
        edge_frequency_min=min(edge_freq_values),
        edge_frequency_max=max(edge_freq_values),
        edge_frequency_mean=edge_frequency_mean,
        edge_frequency_std=edge_frequency_std,
        position_gap_max=max(position_gaps),
        position_gap_mean=sum(position_gaps) / float(len(position_gaps)),
    )


def print_quality(label: str, summary: QualitySummary) -> None:
    coverage = (
        100.0 * summary.edge_count_used / float(summary.edge_count_total)
        if summary.edge_count_total
        else 0.0
    )
    print(
        f"[{label}] itineraries={summary.itinerary_count}, "
        f"edge_coverage={summary.edge_count_used}/{summary.edge_count_total} ({coverage:.1f}%), "
        f"edge_freq[min/max/mean/std]={summary.edge_frequency_min}/"
        f"{summary.edge_frequency_max}/{summary.edge_frequency_mean:.2f}/"
        f"{summary.edge_frequency_std:.2f}, "
        f"node_position_gap[max/mean]={summary.position_gap_max}/"
        f"{summary.position_gap_mean:.2f}"
    )


def load_generation_config(config_path: Path) -> Dict[str, object]:
    if not config_path.exists():
        return {}

    with config_path.open("r", encoding="utf-8") as config_file:
        try:
            config_data = yaml.safe_load(config_file)
        except yaml.YAMLError as config_error:
            raise RuntimeError(f"Unable to parse configuration file: {config_path}") from config_error

    if config_data is None:
        return {}
    if not isinstance(config_data, dict):
        raise ValueError(f"Configuration file {config_path} must contain a top-level mapping.")
    return dict(config_data)


def _coerce_optional_int(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"Configuration field `{field_name}` must be an integer or null.")
    if isinstance(value, int):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return int(stripped)
        except ValueError as value_error:
            raise ValueError(
                f"Configuration field `{field_name}` must be an integer or null."
            ) from value_error
    raise ValueError(f"Configuration field `{field_name}` must be an integer or null.")


def resolve_generation_seed(cli_seed: int | None, config_seed: object) -> int:
    if cli_seed is not None:
        return int(cli_seed)

    parsed_config_seed = _coerce_optional_int(config_seed, "seed")
    if parsed_config_seed is not None:
        return parsed_config_seed

    return random.SystemRandom().randrange(0, 2**32)


def parse_node_name(node_name: str) -> Tuple[int, int]:
    node_match = NODE_PATTERN.match(node_name)
    if node_match is None:
        raise ValueError(f"Invalid node name: {node_name}")
    plane_idx = int(node_match.group(1))
    strip_idx = int(node_match.group(2))
    return plane_idx, strip_idx


def node_plot_coordinates(node_name: str) -> Tuple[float, float]:
    plane_idx, strip_idx = parse_node_name(node_name)
    x_coord = float(strip_idx)
    y_coord = float(4 - plane_idx)
    return x_coord, y_coord


def _stagger_offset(occurrence_index: int, step: float = 0.07) -> float:
    if occurrence_index <= 0:
        return 0.0
    level = (occurrence_index + 1) // 2
    sign = 1.0 if occurrence_index % 2 == 1 else -1.0
    return sign * level * step


def plot_example_itinerary_side_view(
    itinerary: Sequence[str],
    output_path: Path,
    show_plot: bool,
) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError as import_error:
        raise RuntimeError("matplotlib is required to draw itinerary plots.") from import_error

    coordinates = [node_plot_coordinates(node_name) for node_name in itinerary]
    x_values = [x_coord for x_coord, _ in coordinates]
    y_values = [y_coord for _, y_coord in coordinates]
    color_map = plt.get_cmap("viridis")
    color_denominator = max(len(itinerary) - 1, 1)
    node_step_index = {node_name: step_idx for step_idx, node_name in enumerate(itinerary)}

    def _color_fraction(step_index: int, denominator: int) -> float:
        raw_fraction = float(step_index) / float(max(denominator, 1))
        return min(raw_fraction, DEFAULT_COLORMAP_MAX)

    fig, axis = plt.subplots(figsize=(7.0, 7.0))

    for plane_idx in range(1, 5):
        y_coord = float(4 - plane_idx)
        for strip_idx in range(1, 5):
            node_name = f"P{plane_idx}s{strip_idx}"
            if node_name in node_step_index:
                color_value = color_map(_color_fraction(node_step_index[node_name], color_denominator))
            else:
                color_value = "#AEB7BF"
            axis.plot(
                [strip_idx - 0.45, strip_idx + 0.45],
                [y_coord, y_coord],
                color=color_value,
                linewidth=10,
                solid_capstyle="round",
                zorder=1,
            )

    if len(itinerary) > 1:
        from matplotlib.colors import to_rgba

        vertical_segment_counts: Dict[int, int] = {}
        gradient_slices = 18
        for segment_idx in range(len(itinerary) - 1):
            start_color = to_rgba(color_map(_color_fraction(segment_idx, color_denominator)))
            end_color = to_rgba(color_map(_color_fraction(segment_idx + 1, color_denominator)))
            x_start = x_values[segment_idx]
            y_start = y_values[segment_idx]
            x_end = x_values[segment_idx + 1]
            y_end = y_values[segment_idx + 1]

            x_stagger = 0.0
            if abs(x_end - x_start) < 1e-12:
                strip_key = int(round(x_start))
                seen_count = vertical_segment_counts.get(strip_key, 0)
                x_stagger = _stagger_offset(seen_count, step=0.07)
                vertical_segment_counts[strip_key] = seen_count + 1

            x_segment = [x_start + x_stagger, x_end + x_stagger]
            y_segment = [y_start, y_end]

            for slice_idx in range(gradient_slices):
                t_start = float(slice_idx) / float(gradient_slices)
                t_end = float(slice_idx + 1) / float(gradient_slices)
                x_slice = [
                    x_segment[0] + (x_segment[1] - x_segment[0]) * t_start,
                    x_segment[0] + (x_segment[1] - x_segment[0]) * t_end,
                ]
                y_slice = [
                    y_segment[0] + (y_segment[1] - y_segment[0]) * t_start,
                    y_segment[0] + (y_segment[1] - y_segment[0]) * t_end,
                ]
                t_mid = (t_start + t_end) / 2.0
                blended_color = tuple(
                    start_component + (end_component - start_component) * t_mid
                    for start_component, end_component in zip(start_color, end_color)
                )
                axis.plot(
                    x_slice,
                    y_slice,
                    color=blended_color,
                    linewidth=2.8,
                    alpha=0.95,
                    solid_capstyle="butt",
                    zorder=3,
                )

            axis.annotate(
                "",
                xy=(x_segment[1], y_segment[1]),
                xytext=(x_segment[0], y_segment[0]),
                arrowprops={
                    "arrowstyle": "-|>,head_length=0.55,head_width=0.35",
                    "color": end_color,
                    "lw": 1.3,
                    "mutation_scale": 13,
                    "shrinkA": 8,
                    "shrinkB": 4,
                },
                zorder=4,
            )

    label_offsets = (
        (10, 10),
        (-12, 10),
        (10, -11),
        (-12, -11),
    )
    for step_idx, (x_coord, y_coord) in enumerate(coordinates, start=1):
        label_dx, label_dy = label_offsets[(step_idx - 1) % len(label_offsets)]
        axis.annotate(
            str(step_idx),
            xy=(x_coord, y_coord),
            xytext=(label_dx, label_dy),
            textcoords="offset points",
            ha="center",
            va="center",
            fontsize=7,
            color="#101820",
            bbox={
                "boxstyle": "round,pad=0.18",
                "facecolor": "white",
                "edgecolor": "none",
                "alpha": 0.85,
            },
            zorder=6,
        )

    axis.set_xlim(0.45, 4.55)
    axis.set_ylim(-0.55, 3.55)
    axis.set_aspect("equal", adjustable="box")
    axis.set_xticks([1.0, 2.0, 3.0, 4.0], labels=["Strip 1", "Strip 2", "Strip 3", "Strip 4"])
    axis.set_yticks([3.0, 2.0, 1.0, 0.0], labels=["Plane 1", "Plane 2", "Plane 3", "Plane 4"])
    axis.set_xlabel("Strip index")
    axis.set_ylabel("Detector plane")
    axis.set_title("Example Time-Calibration Itinerary (Side View)")
    axis.grid(color="#D0D5DB", linestyle="--", linewidth=0.6, alpha=0.7)

    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=220)
    print(f"Saved itinerary example plot: {output_path}")

    if show_plot:
        plt.show()

    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate balanced and deterministic itineraries for time calibration.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help=(
            "YAML config path. Supports `seed`; if seed is null, "
            "a random seed is used and printed."
        ),
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=ITINERARY_FILE_PATH,
        help="Input itineraries used for empirical edge discovery and optional seeding.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ITINERARY_FILE_PATH,
        help="Destination CSV path for generated itineraries.",
    )
    parser.add_argument(
        "--num-itineraries",
        type=int,
        default=DEFAULT_NUM_ITINERARIES,
        help=f"Number of itineraries to write (default: {DEFAULT_NUM_ITINERARIES}).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Override random seed from CLI (takes precedence over config).",
    )
    parser.add_argument(
        "--candidate-pool",
        type=int,
        default=DEFAULT_CANDIDATE_POOL,
        help=f"Target number of candidate Hamiltonian paths (default: {DEFAULT_CANDIDATE_POOL}).",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=DEFAULT_MAX_ATTEMPTS,
        help=f"Maximum path-sampling attempts (default: {DEFAULT_MAX_ATTEMPTS}).",
    )
    parser.add_argument(
        "--edge-mode",
        choices=("empirical", "structural", "intersection", "union"),
        default="empirical",
        help=(
            "How to build allowed transitions: "
            "`empirical` from input, `structural` from TASK_2 definitions, "
            "`intersection` or `union` between both sets."
        ),
    )
    parser.add_argument(
        "--reverse-pairs",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="When true, select path+reverse pairs to reduce direction bias.",
    )
    parser.add_argument(
        "--include-existing",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="When true, include valid input itineraries in the candidate pool.",
    )
    parser.add_argument(
        "--position-weight",
        type=float,
        default=DEFAULT_POSITION_WEIGHT,
        help=(
            "Relative weight for node-position balancing in selection scoring. "
            f"Higher values prioritize position uniformity (default: {DEFAULT_POSITION_WEIGHT})."
        ),
    )
    parser.add_argument(
        "--plot-example",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Draw an example side-view itinerary plot.",
    )
    parser.add_argument(
        "--show-plot",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Display the example plot window (in addition to saving it).",
    )
    parser.add_argument(
        "--example-index",
        type=int,
        default=0,
        help="Index of the selected itinerary to plot as example.",
    )
    parser.add_argument(
        "--example-plot-path",
        type=Path,
        default=DEFAULT_EXAMPLE_PLOT_PATH,
        help="Output path for the side-view itinerary example plot.",
    )
    parser.add_argument(
        "--plot-only-random",
        action="store_true",
        help=(
            "Skip itinerary generation and only create the plot by choosing one "
            "random itinerary from --input using the resolved seed."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print summary without writing output.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_data = load_generation_config(args.config)
    generation_seed = resolve_generation_seed(args.seed, config_data.get("seed"))
    print(f"Using generation seed: {generation_seed}")

    if args.plot_only_random:
        source_itineraries = load_itineraries_from_file(args.input, required=True)
        if not source_itineraries:
            raise ValueError(f"No itineraries available in {args.input} for plot-only mode.")
        random_generator = random.Random(generation_seed)
        random_index = random_generator.randrange(len(source_itineraries))
        random_itinerary = source_itineraries[random_index]
        print(
            f"Plot-only random mode: selected itinerary index {random_index} "
            f"from {args.input}."
        )
        plot_example_itinerary_side_view(
            itinerary=random_itinerary,
            output_path=args.example_plot_path,
            show_plot=bool(args.show_plot),
        )
        return

    input_required = args.edge_mode in ("empirical", "intersection", "union") or args.include_existing
    input_itineraries = load_itineraries_from_file(args.input, required=input_required)

    structural_edges = structural_edge_set()
    empirical_edges = edge_set_from_itineraries(input_itineraries)

    if args.edge_mode == "empirical":
        allowed_edges = set(empirical_edges)
    elif args.edge_mode == "structural":
        allowed_edges = set(structural_edges)
    elif args.edge_mode == "intersection":
        allowed_edges = structural_edges & empirical_edges
    elif args.edge_mode == "union":
        allowed_edges = structural_edges | empirical_edges
    else:
        raise RuntimeError(f"Unsupported edge mode: {args.edge_mode}")

    if not allowed_edges:
        raise RuntimeError("Allowed edge set is empty. Nothing can be generated.")

    adjacency = build_adjacency(allowed_edges)
    assert_graph_connected(adjacency)

    seed_candidates: List[PathTuple] = []
    if args.include_existing:
        for itinerary in input_itineraries:
            is_valid, _ = validate_itinerary(itinerary, allowed_edges)
            if is_valid:
                seed_candidates.append(tuple(itinerary))

    target_candidate_pool = max(args.candidate_pool, max(args.num_itineraries * 40, 1000))
    candidates, attempts = generate_candidate_paths(
        adjacency=adjacency,
        seed=generation_seed,
        target_unique=target_candidate_pool,
        max_attempts=args.max_attempts,
        initial_candidates=seed_candidates,
    )

    if len(candidates) < args.num_itineraries:
        raise RuntimeError(
            f"Could not collect enough candidates. "
            f"candidates={len(candidates)}, requested={args.num_itineraries}, attempts={attempts}"
        )

    units = build_selection_units(candidates, reverse_pairs=args.reverse_pairs)
    selected_itineraries = select_itineraries(
        units=units,
        num_itineraries=args.num_itineraries,
        reverse_pairs=args.reverse_pairs,
        edge_universe=allowed_edges,
        position_weight=float(args.position_weight),
    )
    validate_itineraries(selected_itineraries, allowed_edges)

    old_summary = summarize_quality(input_itineraries, allowed_edges) if input_itineraries else None
    new_summary = summarize_quality(selected_itineraries, allowed_edges)

    print(
        f"Generation details: edge_mode={args.edge_mode}, seed={generation_seed}, "
        f"candidates={len(candidates)}, attempts={attempts}, "
        f"selection_units={len(units)}, reverse_pairs={args.reverse_pairs}, "
        f"position_weight={float(args.position_weight):.3f}"
    )
    if old_summary is not None:
        print_quality("input", old_summary)
    print_quality("output", new_summary)

    if args.plot_example:
        if args.example_index < 0 or args.example_index >= len(selected_itineraries):
            raise ValueError(
                f"example_index must be within [0, {len(selected_itineraries) - 1}], "
                f"got {args.example_index}."
            )
        example_itinerary = selected_itineraries[args.example_index]
        plot_example_itinerary_side_view(
            itinerary=example_itinerary,
            output_path=args.example_plot_path,
            show_plot=bool(args.show_plot),
        )

    if not args.dry_run:
        write_itineraries_to_file(args.output, selected_itineraries)
        print(f"Wrote {len(selected_itineraries)} itineraries to {args.output}")


if __name__ == "__main__":
    main()
