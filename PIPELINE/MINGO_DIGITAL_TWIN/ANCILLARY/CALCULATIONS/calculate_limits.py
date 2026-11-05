#!/usr/bin/python3

from pathlib import Path
import csv

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


REPO_ROOT = next(
    (parent for parent in Path(__file__).resolve().parents if (parent / "CONTEXTUAL" / "CONFIG" / "config_paths.yaml").is_file()),
    None,
)
if REPO_ROOT is None:
    raise RuntimeError(f"Could not locate repository root from {__file__}")
CONFIG_DIR = REPO_ROOT / "PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/CONFIG_FILES/STAGE_0/ONLINE_RUN_DICTIONARY"
OUTPUT_TABLE_PATH = Path(__file__).with_name("calculate_limits_table.csv")
OUTPUT_PLOT_PATH = Path(__file__).with_name("calculate_limits.png")

z_limit_mm = -100.0
side_mm = 300.0


def analytic_pair_limit_mm(z_a: float, z_b: float) -> float:
    return abs(((z_limit_mm - z_a) / (z_b - z_a) - 0.5) * side_mm)


def final_limit_mm_for_geometry(z_planes_mm: np.ndarray) -> float:
    pair_limits = [
        analytic_pair_limit_mm(z_planes_mm[i], z_planes_mm[i + 1])
        for i in range(len(z_planes_mm) - 1)
    ]
    return float(max(pair_limits))


def load_unique_geometries(config_dir: Path) -> list[tuple[int, int, int, int]]:
    geometries: set[tuple[int, int, int, int]] = set()

    for csv_path in sorted(config_dir.glob("STATION_*/*.csv")):
        with csv_path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.reader(handle))

        if len(rows) < 3:
            continue

        header = rows[1]
        index_by_name = {name: idx for idx, name in enumerate(header)}
        required = ("P1", "P2", "P3", "P4")
        if not all(name in index_by_name for name in required):
            continue

        for row in rows[2:]:
            if len(row) <= index_by_name["P4"]:
                continue
            try:
                geometry = tuple(
                    int(float(row[index_by_name[name]]))
                    for name in required
                )
            except ValueError:
                continue
            geometries.add(geometry)

    return sorted(geometries)


def save_limits_table(
    output_path: Path,
    geometries: list[tuple[int, int, int, int]],
    limits_mm: list[float],
) -> None:
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["z_p1_mm", "z_p2_mm", "z_p3_mm", "z_p4_mm", "limit_mm"])
        for geometry, limit_mm in zip(geometries, limits_mm):
            writer.writerow([*geometry, round(limit_mm, 6)])


def save_summary_plot(
    output_path: Path,
    geometries: list[tuple[int, int, int, int]],
    limits_mm: list[float],
) -> None:
    labels = [f"{p1}/{p2}/{p3}/{p4}" for p1, p2, p3, p4 in geometries]
    x = np.arange(len(labels))

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(x, limits_mm, color="tab:blue")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=30, ha="right")
    ax.set_ylabel("Limit (mm)")
    ax.set_xlabel("z positions P1/P2/P3/P4 (mm)")
    ax.set_title("Simulation transverse limit for each available detector geometry")
    ax.grid(True, axis="y", alpha=0.25)
    plt.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def main() -> None:
    geometries = load_unique_geometries(CONFIG_DIR)
    if not geometries:
        raise RuntimeError(f"No valid geometries found in {CONFIG_DIR}")

    limits_mm = [
        final_limit_mm_for_geometry(np.array(geometry, dtype=float))
        for geometry in geometries
    ]

    save_limits_table(OUTPUT_TABLE_PATH, geometries, limits_mm)
    save_summary_plot(OUTPUT_PLOT_PATH, geometries, limits_mm)

    print(f"Found {len(geometries)} unique geometries")
    print("-" * 30)
    for geometry, limit_mm in zip(geometries, limits_mm):
        print(f"{geometry} -> {limit_mm:.2f} mm")
    print("-" * 30)
    print(f"Table saved to: {OUTPUT_TABLE_PATH}")
    print(f"Plot saved to: {OUTPUT_PLOT_PATH}")


if __name__ == "__main__":
    main()
