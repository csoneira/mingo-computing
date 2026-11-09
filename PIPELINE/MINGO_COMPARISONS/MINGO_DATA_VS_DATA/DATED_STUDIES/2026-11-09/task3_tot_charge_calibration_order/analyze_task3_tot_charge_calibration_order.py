#!/usr/bin/env python3
"""Compare Task-3 charge spectra for the two ToT calibration orders."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import yaml


REPOSITORY_ROOT = next(
    (
        parent
        for parent in Path(__file__).resolve().parents
        if (parent / "CONTEXTUAL" / "CONFIG" / "config_paths.yaml").is_file()
        and (parent / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_SCRIPTS").is_dir()
    ),
    None,
)
if REPOSITORY_ROOT is None:
    raise RuntimeError(f"Could not locate repository root from {__file__}")
sys.path.insert(0, str(REPOSITORY_ROOT))

from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.path_config import (  # noqa: E402
    load_repo_paths,
)
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.tot_charge_calibration import (  # noqa: E402
    TotChargeCalibration,
    default_tot_charge_calibration_path,
)
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.tot_charge_order_comparison import (  # noqa: E402
    calibration_order_arrays,
    plot_calibration_order_comparison,
    plot_calibration_order_scatter,
)


STUDY_ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = STUDY_ROOT / "config.yaml"


def _load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    if not isinstance(config, dict):
        raise ValueError(f"Study config must be a YAML mapping: {path}")
    return config


def _task5_successful_basenames(station_root: Path) -> set[str]:
    task5_root = station_root / "STAGE_1" / "EVENT_DATA" / "STEP_1" / "TASK_5"
    completed_dir = task5_root / "INPUT_FILES" / "COMPLETED_DIRECTORY"
    completed_inputs = {
        path.stem.removeprefix("fitted_")
        for path in completed_dir.glob("fitted_*.parquet")
    }
    status_path = task5_root / "METADATA" / "task_5_metadata_status.csv"
    if not status_path.is_file():
        return set()
    status = pd.read_csv(
        status_path,
        usecols=lambda column: column in {"filename_base", "completion_fraction"},
    )
    if not {"filename_base", "completion_fraction"}.issubset(status.columns):
        return set()
    status["completion_fraction"] = pd.to_numeric(
        status["completion_fraction"], errors="coerce"
    )
    completed_status = set(
        status.loc[status["completion_fraction"] >= 1.0, "filename_base"].astype(str)
    )
    return completed_inputs & completed_status


def _task3_products(station_root: Path, successful_basenames: set[str]) -> list[Path]:
    step_root = station_root / "STAGE_1" / "EVENT_DATA" / "STEP_1"
    product_dirs = (
        step_root / "TASK_3" / "OUTPUT_FILES",
        step_root / "TASK_4" / "INPUT_FILES" / "COMPLETED_DIRECTORY",
    )
    by_basename: dict[str, Path] = {}
    for directory in product_dirs:
        if not directory.is_dir():
            continue
        for path in directory.glob("listed_*.parquet"):
            basename = path.stem.removeprefix("listed_")
            if basename in successful_basenames:
                by_basename.setdefault(basename, path)
    return [by_basename[key] for key in sorted(by_basename)]


def _columns_to_read(path: Path) -> list[str]:
    available = set(pq.ParquetFile(path).schema.names)
    requested = []
    for plane in range(1, 5):
        for strip in range(1, 5):
            requested.extend(
                (
                    f"p{plane}_s{strip}_qsum_cal",
                    f"p{plane}_s{strip}_qsum",
                    f"p{plane}_s{strip}_qsum_fc",
                )
            )
        requested.append(f"p{plane}_qsum_fc")
    return [column for column in requested if column in available]


def analyze_station(
    station: int,
    *,
    max_files: int = 1,
    output_dir: Path | None = None,
    bins: int = 70,
) -> Path:
    paths = load_repo_paths()
    station_root = paths.stations_root / f"MINGO{station:02d}"
    successful = _task5_successful_basenames(station_root)
    products = _task3_products(station_root, successful)
    if max_files < 1:
        raise ValueError("consecutive file count must be positive")
    # Products are sorted by acquisition basename; take the most recent
    # consecutive completed products, not every historical file.
    products = products[-max_files:]
    if not products:
        raise RuntimeError(
            f"No Task-3 listed parquet has a matching Task-5 COMPLETED input and "
            f"completion_fraction=1 for MINGO{station:02d}."
        )

    calibration = TotChargeCalibration.from_csv(
        default_tot_charge_calibration_path(paths.repo_root)
    )
    accumulated: dict[int, dict[str, list[np.ndarray]]] = {
        plane: {
            "sum_ns": [],
            "calibrate_then_sum_fc": [],
            "sum_then_calibrate_fc": [],
        }
        for plane in range(1, 5)
    }
    legacy_fallback_files = 0
    total_rows = 0

    for index, product in enumerate(products, start=1):
        columns = _columns_to_read(product)
        frame = pd.read_parquet(product, columns=columns)
        total_rows += len(frame)
        if "p1_s1_qsum_fc" not in frame.columns:
            legacy_fallback_files += 1
        spectra = calibration_order_arrays(frame, calibration)
        for plane, plane_spectra in spectra.items():
            for name, values in plane_spectra.items():
                accumulated[plane][name].append(values)
        if index % 25 == 0 or index == len(products):
            print(f"Loaded {index}/{len(products)} Task-5-completed Task-3 products")

    joined_spectra: dict[int, dict[str, np.ndarray]] = {}
    for plane, series in accumulated.items():
        joined_spectra[plane] = {
            name: np.concatenate(parts) if parts else np.array([], dtype=float)
            for name, parts in series.items()
        }

    figure = plot_calibration_order_comparison(
        joined_spectra,
        station=station,
        file_count=len(products),
        bins=bins,
    )
    target_dir = output_dir or (STUDY_ROOT / "PLOTS")
    target_dir.mkdir(parents=True, exist_ok=True)
    output_path = target_dir / f"task3_tot_charge_calibration_order_mingo{station:02d}.png"
    figure.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close(figure)
    scatter = plot_calibration_order_scatter(
        joined_spectra,
        station=station,
        file_count=len(products),
    )
    scatter_path = target_dir / f"task3_tot_charge_calibration_order_scatter_mingo{station:02d}.png"
    scatter.savefig(scatter_path, dpi=160, bbox_inches="tight")
    plt.close(scatter)
    print(
        f"Saved {output_path} and {scatter_path}; files={len(products)}, rows={total_rows:,}, "
        f"legacy products recalculated from Task-3 ns columns={legacy_fallback_files}."
    )
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--station", type=int, choices=range(5), default=None)
    parser.add_argument(
        "--max-files",
        type=int,
        default=None,
        help="override the configured number of newest consecutive Task-5-completed files",
    )
    parser.add_argument("--bins", type=int, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()
    config = _load_config(args.config)
    station = args.station if args.station is not None else int(config.get("station", 1))
    max_files = (
        args.max_files
        if args.max_files is not None
        else int(config.get("consecutive_files", 1))
    )
    bins = args.bins if args.bins is not None else int(config.get("histogram_bins", 70))
    analyze_station(
        station,
        max_files=max_files,
        output_dir=args.output_dir,
        bins=bins,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
