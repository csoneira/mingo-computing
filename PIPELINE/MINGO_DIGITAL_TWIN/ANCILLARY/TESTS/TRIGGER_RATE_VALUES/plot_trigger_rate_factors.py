#!/usr/bin/env python3

"""Plot simulated trigger-rate factors versus detector efficiencies."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Iterable

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
DIGITAL_TWIN_DIR = Path(__file__).resolve().parents[3]
DEFAULT_INPUT = DIGITAL_TWIN_DIR / "SIMULATION_OUTPUTS/SIMULATED_DATA/step_final_simulation_params.csv"
DEFAULT_PDF = SCRIPT_DIR / "trigger_rate_efficiency_factors.pdf"
DEFAULT_CSV = SCRIPT_DIR / "trigger_rate_efficiency_factors.csv"

RATE_COLUMNS = (
    "particle_crossing_rate_hz",
    "trigger_rate_unit_efficiency_hz",
    "trigger_rate_hz",
)
GEOMETRY_COLUMNS = tuple(f"z_plane_{plane}" for plane in range(1, 5))
EFFICIENCY_COLUMNS = tuple(f"efficiency_plane_{plane}" for plane in range(1, 5))
FACTOR_COLUMNS = (
    "geometric_trigger_efficiency",
    "conditional_detector_efficiency",
    "overall_detection_efficiency",
)
PLOT_VARIABLES = (
    ("efficiency_plane_1", "Plane 1 efficiency"),
    ("efficiency_plane_2", "Plane 2 efficiency"),
    ("efficiency_plane_3", "Plane 3 efficiency"),
    ("efficiency_plane_4", "Plane 4 efficiency"),
    ("efficiency_mean", "Mean plane efficiency"),
    ("efficiency_product", "Product of four efficiencies"),
)
FACTOR_STYLES = {
    "geometric_trigger_efficiency": ("Geometrical trigger factor", "#1f77b4", "o"),
    "conditional_detector_efficiency": ("Conditional detector factor", "#ff7f0e", "s"),
    "overall_detection_efficiency": ("Overall detection factor", "#2ca02c", "^"),
}


def parse_sequence(value: object, field_name: str) -> list[object]:
    if isinstance(value, (list, tuple, np.ndarray)):
        return list(value)
    if pd.isna(value):
        raise ValueError(f"{field_name} is missing")
    text = str(value).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        try:
            parsed = ast.literal_eval(text)
        except (SyntaxError, ValueError) as exc:
            raise ValueError(f"cannot parse {field_name}: {value!r}") from exc
    if not isinstance(parsed, (list, tuple)):
        raise ValueError(f"{field_name} must contain a list")
    return list(parsed)


def parse_efficiencies(value: object) -> tuple[float, float, float, float]:
    values = parse_sequence(value, "efficiencies")
    if len(values) != 4:
        raise ValueError(f"efficiencies must contain four values, found {len(values)}")
    efficiencies = tuple(float(item) for item in values)
    if not all(np.isfinite(item) and 0.0 < item <= 1.0 for item in efficiencies):
        raise ValueError(f"efficiencies must be finite and in (0, 1], found {efficiencies}")
    return efficiencies  # type: ignore[return-value]


def parse_triggers(value: object) -> tuple[str, ...]:
    values = parse_sequence(value, "trigger_combinations")
    triggers = tuple(str(item).strip() for item in values if str(item).strip())
    if not triggers:
        raise ValueError("trigger_combinations contains no triggers")
    return triggers


def trigger_key(triggers: Iterable[str]) -> str:
    return json.dumps(list(triggers), separators=(",", ":"))


def trigger_label(triggers: Iterable[str]) -> str:
    return " OR ".join(str(trigger) for trigger in triggers)


def prepare_plot_data(raw: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    required = {
        "file_name",
        "efficiencies",
        "trigger_combinations",
        *GEOMETRY_COLUMNS,
        *RATE_COLUMNS,
    }
    missing = sorted(required - set(raw.columns))
    if missing:
        raise ValueError("Input CSV is missing required columns: " + ", ".join(missing))

    work = raw.copy()
    for column in (*GEOMETRY_COLUMNS, *RATE_COLUMNS):
        work[column] = pd.to_numeric(work[column], errors="coerce")

    warnings: list[str] = []
    records: list[dict[str, object]] = []
    for index, row in work.iterrows():
        rates = np.asarray([row[column] for column in RATE_COLUMNS], dtype=float)
        geometry = np.asarray([row[column] for column in GEOMETRY_COLUMNS], dtype=float)
        if not np.isfinite(rates).all() or not np.isfinite(geometry).all():
            continue

        crossing, unit_trigger, actual_trigger = rates
        tolerance = max(1e-12, crossing * 1e-10)
        if (
            crossing <= 0.0
            or unit_trigger < 0.0
            or actual_trigger < 0.0
            or actual_trigger > unit_trigger + tolerance
            or unit_trigger > crossing + tolerance
        ):
            warnings.append(
                f"Skipped row {index} ({row['file_name']}): rate ordering is invalid "
                f"(actual={actual_trigger}, unit={unit_trigger}, crossing={crossing})."
            )
            continue

        try:
            efficiencies = parse_efficiencies(row["efficiencies"])
            triggers = parse_triggers(row["trigger_combinations"])
        except (TypeError, ValueError) as exc:
            warnings.append(f"Skipped row {index} ({row['file_name']}): {exc}.")
            continue

        record = row.to_dict()
        record.update(
            {
                **dict(zip(EFFICIENCY_COLUMNS, efficiencies)),
                "efficiency_mean": float(np.mean(efficiencies)),
                "efficiency_product": float(np.prod(efficiencies)),
                "trigger_configuration": trigger_key(triggers),
                "trigger_label": trigger_label(triggers),
                "geometry_label": ", ".join(
                    f"P{plane}={position:g} mm"
                    for plane, position in enumerate(geometry, start=1)
                ),
                "geometric_trigger_efficiency": unit_trigger / crossing,
                "conditional_detector_efficiency": (
                    actual_trigger / unit_trigger if unit_trigger > 0.0 else np.nan
                ),
                "overall_detection_efficiency": actual_trigger / crossing,
            }
        )
        records.append(record)

    if not records:
        raise ValueError(
            "No rows contain finite decomposed rates and valid efficiency metadata."
        )

    prepared = pd.DataFrame(records)
    prepared = prepared.sort_values(
        ["trigger_configuration", *GEOMETRY_COLUMNS, "efficiency_mean", "file_name"],
        kind="stable",
    ).reset_index(drop=True)
    return prepared, warnings


def plot_panel(
    axis: plt.Axes,
    group: pd.DataFrame,
    x_column: str,
    x_label: str,
) -> None:
    for factor_column in FACTOR_COLUMNS:
        label, color, marker = FACTOR_STYLES[factor_column]
        finite = np.isfinite(group[x_column]) & np.isfinite(group[factor_column])
        subset = group.loc[finite].sort_values(x_column, kind="stable")
        if subset.empty:
            continue
        axis.scatter(
            subset[x_column],
            subset[factor_column],
            label=label,
            color=color,
            marker=marker,
            s=48,
            alpha=0.82,
            edgecolors="white",
            linewidths=0.45,
            zorder=3,
        )
        if subset[x_column].nunique() > 1:
            axis.plot(
                subset[x_column],
                subset[factor_column],
                color=color,
                linewidth=1.0,
                alpha=0.42,
                zorder=2,
            )
    axis.set_title(x_label)
    axis.set_xlabel(x_label)
    axis.set_ylabel("Efficiency factor")
    axis.set_ylim(-0.02, 1.02)
    axis.grid(True, alpha=0.25)
    axis.set_axisbelow(True)


def write_pdf(prepared: pd.DataFrame, output: Path, source: Path) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    group_columns = ["trigger_configuration", *GEOMETRY_COLUMNS]
    page_count = 0
    with PdfPages(
        output,
        metadata={
            "Title": "Trigger-rate factors versus detector efficiencies",
            "Subject": "One page per trigger configuration and geometry",
        },
    ) as pdf:
        for key, group in prepared.groupby(group_columns, sort=True, dropna=False):
            triggers = json.loads(str(key[0]))
            geometry = tuple(float(value) for value in key[1:])
            figure, axes = plt.subplots(2, 3, figsize=(18, 10))
            for axis, (x_column, x_label) in zip(axes.flat, PLOT_VARIABLES):
                plot_panel(axis, group, x_column, x_label)

            handles, labels = axes.flat[0].get_legend_handles_labels()
            if handles:
                figure.legend(
                    handles,
                    labels,
                    loc="upper center",
                    ncol=3,
                    frameon=False,
                    bbox_to_anchor=(0.5, 0.94),
                )
            geometry_text = ", ".join(
                f"P{plane}={position:g} mm"
                for plane, position in enumerate(geometry, start=1)
            )
            figure.suptitle(
                "Trigger-rate efficiency factors\n"
                f"Trigger configuration: {trigger_label(triggers)} | "
                f"Geometry: {geometry_text}",
                fontsize=15,
                y=0.995,
            )
            figure.text(
                0.01,
                0.012,
                f"Rows on page: {len(group)} | Source: {source}",
                fontsize=8,
                color="0.35",
            )
            figure.tight_layout(rect=(0.0, 0.035, 1.0, 0.90))
            pdf.savefig(figure, dpi=160)
            plt.close(figure)
            page_count += 1
    return page_count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Plot geometrical, conditional-detector, and overall trigger factors "
            "versus individual, mean, and product plane efficiencies."
        )
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-pdf", type=Path, default=DEFAULT_PDF)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_CSV)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.input.expanduser().resolve()
    output_pdf = args.output_pdf.expanduser().resolve()
    output_csv = args.output_csv.expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(f"Input CSV does not exist: {source}")

    raw = pd.read_csv(source)
    prepared, warnings = prepare_plot_data(raw)
    for warning in warnings:
        print(f"[WARN] {warning}")

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    prepared.to_csv(output_csv, index=False)
    pages = write_pdf(prepared, output_pdf, source)
    groups = prepared.groupby(["trigger_configuration", *GEOMETRY_COLUMNS]).ngroups

    print(f"Input rows: {len(raw):,}")
    print(f"Rows with valid decomposed rates: {len(prepared):,}")
    print(f"Distinct trigger/geometry pages: {groups:,}")
    print(f"Saved {pages}-page PDF: {output_pdf}")
    print(f"Saved plotted values: {output_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
