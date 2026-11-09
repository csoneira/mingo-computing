"""Bounded-memory reductions for configurable event-gate analyses."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd


COUNTED_TOPOLOGIES = ("123", "124", "134", "234", "1234")
MISSING_TOPOLOGY = {1: "234", 2: "134", 3: "124", 4: "123"}


@dataclass
class StreamingPlaneEfficiencyMaps:
    """Exact fixed-bin detected/missing projected-position maps."""

    setting: Mapping[str, Any]
    x_edges: np.ndarray
    y_edges: np.ndarray
    detected_counts: dict[tuple[str, int], np.ndarray] = field(
        default_factory=dict
    )
    missing_counts: dict[tuple[str, int], np.ndarray] = field(
        default_factory=dict
    )
    detected_outside: dict[tuple[str, int], int] = field(
        default_factory=lambda: defaultdict(int)
    )
    missing_outside: dict[tuple[str, int], int] = field(
        default_factory=lambda: defaultdict(int)
    )

    def accumulate(
        self,
        frame: pd.DataFrame,
        topologies: pd.Series,
        masks: Mapping[str, pd.Series],
    ) -> None:
        x0 = pd.to_numeric(
            frame[self.setting["x_column"]], errors="coerce",
        ).to_numpy(dtype=float)
        y0 = pd.to_numeric(
            frame[self.setting["y_column"]], errors="coerce",
        ).to_numpy(dtype=float)
        xp = pd.to_numeric(
            frame[self.setting["x_slope_column"]], errors="coerce",
        ).to_numpy(dtype=float)
        yp = pd.to_numeric(
            frame[self.setting["y_slope_column"]], errors="coerce",
        ).to_numpy(dtype=float)
        topology_values = (
            topologies.astype("string").fillna("").to_numpy(dtype=str)
        )
        for plane, z_column in enumerate(self.setting["z_columns"], 1):
            z = pd.to_numeric(frame[z_column], errors="coerce").to_numpy(dtype=float)
            x = x0 + xp * z
            y = y0 + yp * z
            finite = np.isfinite(x) & np.isfinite(y)
            missing_topology = MISSING_TOPOLOGY[plane]
            for gate_code, gate_mask in masks.items():
                selected_gate = gate_mask.to_numpy(dtype=bool)
                key = (str(gate_code), plane)
                for topology, destination, outside_destination in (
                    (
                        "1234",
                        self.detected_counts,
                        self.detected_outside,
                    ),
                    (
                        missing_topology,
                        self.missing_counts,
                        self.missing_outside,
                    ),
                ):
                    selected = (
                        finite
                        & selected_gate
                        & (topology_values == topology)
                    )
                    histogram = np.histogram2d(
                        x[selected],
                        y[selected],
                        bins=(self.x_edges, self.y_edges),
                    )[0].astype(np.int64)
                    if key in destination:
                        destination[key] += histogram
                    else:
                        destination[key] = histogram
                    outside_destination[key] += int(
                        np.count_nonzero(selected) - histogram.sum()
                    )


@dataclass
class StreamingPlaneXYHistograms:
    """Exact fixed-bin projected X/Y histograms split by gate and plane."""

    setting: Mapping[str, Any]
    x_edges: np.ndarray
    y_edges: np.ndarray
    counts: dict[tuple[str, int], np.ndarray] = field(default_factory=dict)
    outside: dict[tuple[str, int], int] = field(
        default_factory=lambda: defaultdict(int)
    )

    def accumulate(
        self,
        frame: pd.DataFrame,
        masks: Mapping[str, pd.Series],
    ) -> None:
        x0 = pd.to_numeric(
            frame[self.setting["x_column"]], errors="coerce",
        ).to_numpy(dtype=float)
        y0 = pd.to_numeric(
            frame[self.setting["y_column"]], errors="coerce",
        ).to_numpy(dtype=float)
        xp = pd.to_numeric(
            frame[self.setting["x_slope_column"]], errors="coerce",
        ).to_numpy(dtype=float)
        yp = pd.to_numeric(
            frame[self.setting["y_slope_column"]], errors="coerce",
        ).to_numpy(dtype=float)
        for plane, z_column in enumerate(self.setting["z_columns"], 1):
            z = pd.to_numeric(frame[z_column], errors="coerce").to_numpy(dtype=float)
            x = x0 + xp * z
            y = y0 + yp * z
            finite = np.isfinite(x) & np.isfinite(y)
            for gate_code, gate_mask in masks.items():
                selected = finite & gate_mask.to_numpy(dtype=bool)
                histogram = np.histogram2d(
                    x[selected], y[selected], bins=(self.x_edges, self.y_edges),
                )[0].astype(np.int64)
                key = (str(gate_code), plane)
                if key in self.counts:
                    self.counts[key] += histogram
                else:
                    self.counts[key] = histogram
                self.outside[key] += int(np.count_nonzero(selected) - histogram.sum())


@dataclass
class StreamingChargeClusterHistograms:
    """Exact fixed-bin plane-charge histograms split by gate and cluster size."""

    edges: np.ndarray
    counts: dict[tuple[str, int, int], np.ndarray] = field(default_factory=dict)
    underflow: dict[tuple[str, int, int], int] = field(
        default_factory=lambda: defaultdict(int)
    )
    overflow: dict[tuple[str, int, int], int] = field(
        default_factory=lambda: defaultdict(int)
    )

    def accumulate(
        self,
        frame: pd.DataFrame,
        masks: Mapping[str, pd.Series],
    ) -> None:
        lower, upper = float(self.edges[0]), float(self.edges[-1])
        for plane in range(1, 5):
            charges = pd.to_numeric(
                frame[f"p{plane}_qsum"], errors="coerce",
            ).to_numpy(dtype=float)
            cluster_sizes = pd.to_numeric(
                frame[f"p{plane}_cluster_size"], errors="coerce",
            ).to_numpy(dtype=float)
            finite = np.isfinite(charges) & np.isfinite(cluster_sizes)
            for gate_code, gate_mask in masks.items():
                selected_gate = gate_mask.to_numpy(dtype=bool)
                for cluster_size in range(1, 5):
                    selected = charges[
                        finite
                        & selected_gate
                        & (cluster_sizes == cluster_size)
                    ]
                    key = (str(gate_code), plane, cluster_size)
                    histogram = np.histogram(
                        selected, bins=self.edges,
                    )[0].astype(np.int64)
                    if key in self.counts:
                        self.counts[key] += histogram
                    else:
                        self.counts[key] = histogram
                    self.underflow[key] += int(
                        np.count_nonzero(selected < lower)
                    )
                    self.overflow[key] += int(
                        np.count_nonzero(selected > upper)
                    )


@dataclass
class StreamingAngularHistograms:
    """Exact, mergeable angular-histogram reductions."""

    setting: Mapping[str, Any]
    histogram_counts: dict[tuple[str, str, str], np.ndarray] = field(default_factory=dict)
    finite_counts: dict[tuple[str, str, str], int] = field(default_factory=lambda: defaultdict(int))
    asymmetry_left_counts: dict[tuple[str, str], np.ndarray] = field(default_factory=dict)
    asymmetry_totals: dict[tuple[str, str], int] = field(default_factory=lambda: defaultdict(int))
    z_ranges: dict[str, tuple[float, float]] = field(default_factory=dict)

    def _values(self, frame: pd.DataFrame, variable: Mapping[str, Any]) -> np.ndarray:
        values = pd.to_numeric(frame[variable["column"]], errors="coerce").to_numpy(dtype=float)
        sign_column = variable.get("sign_by_cosine_column")
        if sign_column:
            direction = pd.to_numeric(frame[sign_column], errors="coerce").to_numpy(dtype=float)
            values = np.where(
                np.isfinite(direction),
                values * np.where(np.cos(direction) >= 0, 1.0, -1.0),
                np.nan,
            )
        if self.setting["degrees"]:
            values = np.degrees(values)
        return values

    def _selections(
        self, gate_codes: pd.Series, masks: Mapping[str, pd.Series],
    ) -> dict[tuple[str, str], np.ndarray]:
        selections = {
            ("individual", str(code)): mask.to_numpy(dtype=bool)
            for code, mask in masks.items()
        }
        if self.setting["include_combined_exact"]:
            codes = gate_codes.astype("string").to_numpy()
            for code in pd.unique(codes):
                if pd.isna(code):
                    continue
                code = str(code)
                if code == "0" and not self.setting["include_combined_zero"]:
                    continue
                selections[("combined_exact", code)] = codes == code
        return selections

    def accumulate(
        self, frame: pd.DataFrame, gate_codes: pd.Series, masks: Mapping[str, pd.Series],
    ) -> None:
        selections = self._selections(gate_codes, masks)
        values_by_slug: dict[str, np.ndarray] = {}
        for variable in self.setting["variables"]:
            slug = variable["slug"]
            values = self._values(frame, variable)
            values_by_slug[slug] = values
            finite = np.isfinite(values)
            edges = np.linspace(variable["range"][0], variable["range"][1], variable["bins"] + 1)
            for (kind, code), selected in selections.items():
                chosen = values[finite & selected]
                key = (slug, kind, code)
                counts = np.histogram(chosen, bins=edges)[0].astype(np.int64)
                if key in self.histogram_counts:
                    self.histogram_counts[key] += counts
                else:
                    self.histogram_counts[key] = counts
                self.finite_counts[key] += int(chosen.size)

        for column in self.setting["z_columns"]:
            values = pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype=float)
            values = values[np.isfinite(values)]
            if not values.size:
                continue
            batch_range = (float(values.min()), float(values.max()))
            previous = self.z_ranges.get(column)
            self.z_ranges[column] = (
                batch_range if previous is None
                else (min(previous[0], batch_range[0]), max(previous[1], batch_range[1]))
            )

        asymmetry = self.setting.get("phi_asymmetry")
        if asymmetry is None:
            return
        phi = values_by_slug[asymmetry["variable"]["slug"]]
        finite = np.isfinite(phi)
        period = 360.0 if self.setting["degrees"] else 2.0 * np.pi
        half_period = period / 2.0
        configured_step = float(asymmetry["cut_step"])
        step = configured_step if self.setting["degrees"] else np.radians(configured_step)
        cuts = np.arange(-half_period / 2.0, half_period / 2.0, step)
        for key, selected in selections.items():
            chosen = phi[finite & selected]
            left = np.asarray([
                np.count_nonzero((chosen - cut + half_period) % period - half_period < 0.0)
                for cut in cuts
            ], dtype=np.int64)
            if key in self.asymmetry_left_counts:
                self.asymmetry_left_counts[key] += left
            else:
                self.asymmetry_left_counts[key] = left
            self.asymmetry_totals[key] += int(chosen.size)


@dataclass
class StreamingGateAggregates:
    """Exact reductions whose size scales with windows rather than event rows."""

    window: pd.Timedelta
    total_events: int = 0
    individual_totals: dict[str, int] = field(
        default_factory=lambda: defaultdict(int)
    )
    combined_totals: dict[str, int] = field(
        default_factory=lambda: defaultdict(int)
    )
    window_totals: dict[int, int] = field(
        default_factory=lambda: defaultdict(int)
    )
    observed_second_bits: dict[int, int] = field(
        default_factory=lambda: defaultdict(int)
    )
    individual_window_counts: dict[tuple[int, str], int] = field(
        default_factory=lambda: defaultdict(int)
    )
    combined_window_counts: dict[tuple[int, str], int] = field(
        default_factory=lambda: defaultdict(int)
    )
    individual_topology_counts: dict[tuple[int, str, str], int] = field(
        default_factory=lambda: defaultdict(int)
    )
    combined_topology_counts: dict[tuple[int, str, str], int] = field(
        default_factory=lambda: defaultdict(int)
    )
    angular_histograms: StreamingAngularHistograms | None = None
    charge_cluster_histograms: StreamingChargeClusterHistograms | None = None
    plane_xy_histograms: StreamingPlaneXYHistograms | None = None
    plane_efficiency_maps: StreamingPlaneEfficiencyMaps | None = None

    def __post_init__(self) -> None:
        window_ns = int(self.window.value)
        if window_ns <= 0 or window_ns % 1_000_000_000:
            raise ValueError("Streaming accumulation window must be a positive whole number of seconds")

    @property
    def windows(self) -> list[int]:
        return sorted(self.window_totals)

    def observed_seconds(self, window_ns: int) -> int:
        return int(self.observed_second_bits.get(window_ns, 0)).bit_count()

    def accumulate(
        self,
        timestamps: pd.Series,
        topologies: pd.Series,
        gate_codes: pd.Series,
        masks: Mapping[str, pd.Series],
    ) -> None:
        """Reduce one independently disposable event batch."""
        if not (
            len(timestamps) == len(topologies) == len(gate_codes)
            and all(len(mask) == len(timestamps) for mask in masks.values())
        ):
            raise ValueError("Streaming event inputs must have equal lengths")

        size = len(timestamps)
        self.total_events += size
        codes = gate_codes.astype("string")
        for code, count in codes.value_counts(dropna=False).items():
            if pd.notna(code):
                self.combined_totals[str(code)] += int(count)
        for code, mask in masks.items():
            self.individual_totals[code] += int(mask.to_numpy(dtype=bool).sum())

        parsed_time = pd.to_datetime(timestamps, errors="coerce")
        valid_time = parsed_time.notna()
        if not bool(valid_time.any()):
            return
        windows = parsed_time.loc[valid_time].dt.floor(self.window)
        seconds = parsed_time.loc[valid_time].dt.floor("s")
        window_ns = windows.astype("int64")
        second_ns = seconds.astype("int64")

        for value, count in window_ns.value_counts(sort=False).items():
            self.window_totals[int(value)] += int(count)
        unique_seconds = pd.DataFrame({
            "window": window_ns.to_numpy(),
            "second": second_ns.to_numpy(),
        }).drop_duplicates()
        for window_value, second_value in unique_seconds.itertuples(index=False):
            offset = (int(second_value) - int(window_value)) // 1_000_000_000
            self.observed_second_bits[int(window_value)] |= 1 << int(offset)

        valid_indices = np.flatnonzero(valid_time.to_numpy())
        valid_windows = window_ns.to_numpy()
        valid_topologies = topologies.iloc[valid_indices].astype("string").to_numpy()
        valid_codes = codes.iloc[valid_indices].to_numpy()
        valid_masks = {
            code: mask.iloc[valid_indices].to_numpy(dtype=bool)
            for code, mask in masks.items()
        }

        self._accumulate_selections(
            valid_windows,
            valid_topologies,
            valid_masks,
            self.individual_window_counts,
            self.individual_topology_counts,
        )
        combined_masks = {
            str(code): valid_codes == code
            for code in pd.unique(valid_codes)
            if pd.notna(code)
        }
        self._accumulate_selections(
            valid_windows,
            valid_topologies,
            combined_masks,
            self.combined_window_counts,
            self.combined_topology_counts,
        )

    @staticmethod
    def _accumulate_selections(
        windows: np.ndarray,
        topologies: np.ndarray,
        selections: Mapping[str, np.ndarray],
        window_counts: dict[tuple[int, str], int],
        topology_counts: dict[tuple[int, str, str], int],
    ) -> None:
        for code, selected in selections.items():
            if not bool(np.any(selected)):
                continue
            selected_windows = windows[selected]
            selected_topologies = topologies[selected]
            window_values, counts = np.unique(selected_windows, return_counts=True)
            for window_value, count in zip(window_values, counts, strict=True):
                window_counts[(int(window_value), code)] += int(count)
            grouped = pd.DataFrame({
                "window": selected_windows,
                "topology": selected_topologies,
            }).dropna().groupby(["window", "topology"], sort=False).size()
            for (window_value, topology), count in grouped.items():
                topology_counts[(int(window_value), code, str(topology))] += int(count)


def _code_order(code: str) -> int:
    return int(code)


def gate_summary_frame(
    aggregates: StreamingGateAggregates,
    gates: Sequence[Any],
) -> pd.DataFrame:
    total = aggregates.total_events
    rows: list[dict[str, Any]] = []
    for gate in gates:
        count = int(aggregates.individual_totals.get(gate.code, 0))
        rows.append({
            "kind": "individual",
            "gate_code": gate.code,
            "gate_name": gate.name,
            "gate_label": gate.short_label or gate.name,
            "events": count,
            "fraction": count / total if total else np.nan,
        })
    for code in sorted(aggregates.combined_totals, key=_code_order):
        count = int(aggregates.combined_totals[code])
        value = _code_order(code)
        selected = [gate for gate in gates if value & gate.bit_value]
        rows.append({
            "kind": "combined_exact",
            "gate_code": code,
            "gate_name": " + ".join(gate.name for gate in selected) or "no configured gate",
            "gate_label": "+".join(
                gate.short_label or gate.name for gate in selected
            ) or "None",
            "events": count,
            "fraction": count / total if total else np.nan,
        })
    return pd.DataFrame(rows)


def gate_rate_frame(
    aggregates: StreamingGateAggregates,
    gates: Sequence[Any],
) -> pd.DataFrame:
    combined_codes = sorted(aggregates.combined_totals, key=_code_order)
    rows: list[dict[str, Any]] = []
    for window_ns in aggregates.windows:
        row: dict[str, Any] = {
            "window_start": pd.Timestamp(window_ns),
            "window_end": pd.Timestamp(window_ns) + aggregates.window,
            "observed_seconds": aggregates.observed_seconds(window_ns),
            "total_events": int(aggregates.window_totals[window_ns]),
        }
        for gate in gates:
            row[f"individual_{gate.code}_events"] = int(
                aggregates.individual_window_counts.get((window_ns, gate.code), 0)
            )
        for code in combined_codes:
            row[f"combined_{code}_events"] = int(
                aggregates.combined_window_counts.get((window_ns, code), 0)
            )
        denominator = row["observed_seconds"]
        for name, value in tuple(row.items()):
            if name.endswith("_events"):
                row[name.removesuffix("_events") + "_hz"] = (
                    value / denominator if denominator else np.nan
                )
        rows.append(row)
    return pd.DataFrame(rows)


def _selection_specs(
    aggregates: StreamingGateAggregates,
    gates: Sequence[Any],
    setting: Mapping[str, Any],
) -> list[tuple[str, str, str]]:
    specs = setting.get("selections")
    if specs is None:
        selected: list[tuple[str, str, str]] = [
            ("individual", gate.code, f"{gate.code}: {gate.name}") for gate in gates
        ]
        selected.extend(
            (
                "combined_exact",
                code,
                f"{code}: " + (
                    " + ".join(
                        gate.name for gate in gates
                        if _code_order(code) & gate.bit_value
                    ) or "no configured gate"
                ),
            )
            for code in sorted(aggregates.combined_totals, key=_code_order)
            if code != "0" or setting.get("include_combined_zero", False)
        )
        return selected
    gate_names = {gate.code: gate.name for gate in gates}
    selected = []
    for spec in specs:
        kind, code = spec["kind"], spec["code"]
        default = (
            f"{code}: {gate_names[code]}"
            if kind == "individual"
            else f"{code}: " + (
                " + ".join(
                    gate.name for gate in gates
                    if _code_order(code) & gate.bit_value
                ) or "no configured gate"
            )
        )
        selected.append((kind, code, spec.get("label") or default))
    return selected


def efficiency_summary_frame(
    aggregates: StreamingGateAggregates,
    gates: Sequence[Any],
    setting: Mapping[str, Any],
) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    windows = aggregates.windows
    for kind, code, label in _selection_specs(aggregates, gates, setting):
        counter = (
            aggregates.individual_topology_counts
            if kind == "individual"
            else aggregates.combined_topology_counts
        )
        data: dict[str, Any] = {
            "window_start": [pd.Timestamp(value) for value in windows],
            "window_end": [
                pd.Timestamp(value) + aggregates.window for value in windows
            ],
            "selection_kind": kind,
            "gate_code": code,
            "gate_name": label,
        }
        for topology in COUNTED_TOPOLOGIES:
            data[f"topology_{topology}_count"] = [
                int(counter.get((window, code, topology), 0)) for window in windows
            ]
        summary = pd.DataFrame(data)
        detected = summary["topology_1234_count"].to_numpy(dtype=float)
        for plane, missing in MISSING_TOPOLOGY.items():
            undetected = summary[f"topology_{missing}_count"].to_numpy(dtype=float)
            total = detected + undetected
            summary[f"plane_{plane}_undetected_count"] = undetected.astype(np.int64)
            summary[f"plane_{plane}_total_count"] = total.astype(np.int64)
            summary[f"plane_{plane}_efficiency"] = np.divide(
                detected, total, out=np.full(len(total), np.nan), where=total > 0,
            )
        rows.append(summary)
    return pd.concat(rows, ignore_index=True)


def enabled_gate_comparison_frame(
    aggregates: StreamingGateAggregates,
    gates: Sequence[Any],
    efficiency_product_planes: Sequence[int] = (1, 2, 3, 4),
    efficiency_product_mode: str = "all_planes",
) -> pd.DataFrame:
    windows = aggregates.windows
    rows: list[pd.DataFrame] = []
    for gate in gates:
        data: dict[str, Any] = {
            "window_start": [pd.Timestamp(value) for value in windows],
            "window_end": [
                pd.Timestamp(value) + aggregates.window for value in windows
            ],
            "gate_code": gate.code,
            "gate_name": gate.name,
            "gate_label": gate.short_label or gate.name,
            "observed_seconds": [
                aggregates.observed_seconds(value) for value in windows
            ],
            "gate_event_count": [
                int(aggregates.individual_window_counts.get((value, gate.code), 0))
                for value in windows
            ],
        }
        for topology in COUNTED_TOPOLOGIES:
            data[f"topology_{topology}_count"] = [
                int(aggregates.individual_topology_counts.get(
                    (value, gate.code, topology), 0
                ))
                for value in windows
            ]
        summary = pd.DataFrame(data)
        detected = summary["topology_1234_count"].to_numpy(dtype=float)
        for plane, missing in MISSING_TOPOLOGY.items():
            undetected = summary[f"topology_{missing}_count"].to_numpy(dtype=float)
            denominator = detected + undetected
            summary[f"plane_{plane}_efficiency"] = np.divide(
                detected,
                denominator,
                out=np.full(len(denominator), np.nan),
                where=denominator > 0,
            )
        product_columns = [
            f"plane_{plane}_efficiency" for plane in efficiency_product_planes
        ]
        summary["efficiency_product"] = summary[product_columns].prod(
            axis=1, min_count=len(product_columns)
        )
        summary["efficiency_product_mode"] = efficiency_product_mode
        summary["efficiency_product_plane_numbers"] = ",".join(
            str(plane) for plane in efficiency_product_planes
        )
        observed = summary["observed_seconds"].to_numpy(dtype=float)
        summary["total_gate_rate_hz"] = np.divide(
            summary["gate_event_count"].to_numpy(dtype=float),
            observed,
            out=np.full(len(observed), np.nan),
            where=observed > 0,
        )
        summary["topology_1234_rate_hz"] = np.divide(
            detected,
            observed,
            out=np.full(len(observed), np.nan),
            where=observed > 0,
        )
        efficiency = summary["efficiency_product"].to_numpy(dtype=float)
        rate = summary["topology_1234_rate_hz"].to_numpy(dtype=float)
        summary["corrected_1234_rate_hz"] = np.divide(
            rate,
            efficiency,
            out=np.full(len(rate), np.nan),
            where=np.isfinite(efficiency) & (efficiency > 0),
        )
        rows.append(summary)
    return pd.concat(rows, ignore_index=True)
