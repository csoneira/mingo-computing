#!/usr/bin/env python3
"""Normalize STEP_1 metadata CSVs to one-information-element-per-column."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.step1_shared import normalize_metadata_file_schema


TARGET_BOOLEAN_COLUMNS = frozenset(
    {
        "correct_angle",
        "efficiency_metadata_available",
        "timtrack_projection_ellipse_available",
        "timtrack_projection_ellipse_tt_1234_available",
        "timtrack_projection_ellipse_tt_123_available",
        "timtrack_projection_ellipse_tt_124_available",
        "timtrack_projection_ellipse_tt_134_available",
        "timtrack_projection_ellipse_tt_234_available",
    }
)


def _metadata_paths(repo_root: Path) -> list[Path]:
    return sorted(
        repo_root.glob("PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO0*/STAGE_1/EVENT_DATA/STEP_1/TASK_*/METADATA/*.csv")
    )


def _needs_normalization(path: Path) -> bool:
    try:
        with path.open("r", newline="") as handle:
            reader = csv.DictReader(handle)
            header = list(reader.fieldnames or [])
            rows = []
            for idx, row in enumerate(reader):
                rows.append(row)
                if idx >= 24:
                    break
    except Exception:
        return False

    header_set = {str(value).strip() for value in header if str(value).strip()}
    if "timtrack_projection_ellipse_contour_fractions" in header_set:
        return True
    if any(column.endswith("_Q_FB_coeffs") for column in header_set):
        return True

    bool_columns = header_set & TARGET_BOOLEAN_COLUMNS
    if not bool_columns:
        return False

    for row in rows:
        for column in bool_columns:
            value = str(row.get(column, "")).strip().lower()
            if value in {"true", "false"}:
                return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        help="Optional metadata CSV paths. Defaults to the STEP_1 metadata tree.",
    )
    args = parser.parse_args()

    candidate_paths = [Path(path).expanduser().resolve() for path in args.paths] if args.paths else _metadata_paths(REPO_ROOT)
    target_paths = [path for path in candidate_paths if path.exists() and _needs_normalization(path)]

    print(f"Discovered {len(target_paths)} metadata CSVs requiring schema normalization.")
    for path in target_paths:
        print(f"Normalizing {path}")
        normalize_metadata_file_schema(path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
