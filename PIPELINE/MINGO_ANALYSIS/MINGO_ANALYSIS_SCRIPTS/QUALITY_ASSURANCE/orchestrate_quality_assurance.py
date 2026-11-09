#!/usr/bin/env python3
"""Run configured QUALITY_ASSURANCE steps and rebuild TOTAL_SUMMARY."""

from __future__ import annotations

from pathlib import Path
import argparse
import csv
import fcntl
import filecmp
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from typing import Any

QA_ROOT = Path(__file__).resolve().parent
REPO_ROOT = QA_ROOT.parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.QUALITY_ASSURANCE.qa_core.common import load_yaml_mapping, normalize_station_name
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.QUALITY_ASSURANCE.qa_core.runner import rebuild_step_summaries, run_step
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.QUALITY_ASSURANCE.qa_core.total_summary import build_total_summary
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.QUALITY_ASSURANCE.build_problematic_basename_lists import build_from_file



FILE_BASENAME_RE = re.compile(r"(mi0[0-4]\d{11})", re.IGNORECASE)


def _metadata_basename(value: str) -> str | None:
    match = FILE_BASENAME_RE.search(value)
    return match.group(1).lower() if match else None


def _metadata_timestamp(value: str) -> float:
    """Return a comparable timestamp, with malformed or empty values first."""
    text = (value or "").strip()
    if not text:
        return float("-inf")
    for fmt in ("%Y-%m-%d_%H.%M.%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return float("-inf")


def _is_valid_parquet(path: Path) -> bool:
    """Perform the inexpensive Parquet magic-byte completion check."""
    try:
        if not path.is_file() or path.stat().st_size < 8:
            return False
        with path.open("rb") as handle:
            if handle.read(4) != b"PAR1":
                return False
            handle.seek(-4, os.SEEK_END)
            return handle.read(4) == b"PAR1"
    except OSError:
        return False


def _valid_lake_basenames(lake_dir: Path) -> set[str]:
    valid: set[str] = set()
    for path in lake_dir.glob("postprocessed_*.parquet"):
        base = _metadata_basename(path.name)
        if base is not None and _is_valid_parquet(path):
            valid.add(base)
    return valid


def _write_lake_gated_metadata(
    source_path: Path,
    destination_path: Path,
    valid_lake_bases: set[str],
) -> bool:
    """Publish the newest source row per basename only after final archival.

    ``STAGE_1_PRODUCTS/EVENT_DATA/METADATA`` is a completed-file index. Working
    task metadata remains in ``STAGE_1/EVENT_DATA/STEP_1`` while processing is
    incomplete. A basename becomes eligible here only when its valid final
    Parquet is already present in the station Parquet Lake.
    """
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    with source_path.open("r", encoding="utf-8-sig", newline="") as source_handle:
        reader = csv.reader(source_handle)
        header = next(reader, None)
        if not header:
            return False

        # Reprocessing may append multiple executions. Keep exactly the latest
        # values so product metadata always describes the current lake product.
        newest: dict[str, tuple[float, int, list[str]]] = {}
        for row_number, row in enumerate(reader):
            if not row:
                continue
            base = _metadata_basename(row[0])
            if base is None or base not in valid_lake_bases:
                continue
            timestamp = _metadata_timestamp(row[1] if len(row) > 1 else "")
            previous = newest.get(base)
            candidate = (timestamp, row_number, row)
            if previous is None or candidate[:2] >= previous[:2]:
                newest[base] = candidate

    rows = [
        candidate[2]
        for candidate in sorted(newest.values(), key=lambda item: item[1])
    ]
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=destination_path.parent,
            prefix=f".{destination_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_handle:
            temporary_name = temporary_handle.name
            writer = csv.writer(temporary_handle)
            writer.writerow(header)
            writer.writerows(rows)
            temporary_handle.flush()
            os.fsync(temporary_handle.fileno())

        temporary_path = Path(temporary_name)
        if destination_path.exists() and filecmp.cmp(
            temporary_path, destination_path, shallow=False
        ):
            temporary_path.unlink()
            temporary_name = None
            return False
        os.replace(temporary_path, destination_path)
        temporary_name = None
        return True
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


ARCHIVE_ROOT_NAME = "ARCHIVED_RUN_OUTPUTS"
ARCHIVE_PREVIOUS_NAME = "PREVIOUS_RUN"
ARCHIVE_STAGING_NAME = ".PREVIOUS_RUN_BUILDING"
REPROCESSING_AUTHORITY_RELATIVE_PATH = (
    Path("FILES") / "qa_all_stations_reprocessing_quality.csv"
)


def _rotate_output_directory(
    output_dir: Path,
    archive_destination: Path,
    *,
    preserve_relative_paths: frozenset[Path] = frozenset(),
) -> tuple[int, int]:
    """Archive outputs while optionally retaining live authority files.

    Retained files are copied into the prior-run archive and left at their
    active path until the new generation replaces them atomically. This keeps
    cron consumers from observing a missing authority file during a rebuild.
    """
    if not output_dir.is_dir():
        return 0, 0

    current_children = [
        child for child in output_dir.iterdir()
        if child.name != ARCHIVE_STAGING_NAME
    ]
    if not current_children:
        return 0, 0

    moved_files = 0
    moved_bytes = 0
    for child in current_children:
        paths = [child] if child.is_file() else child.rglob("*")
        for path in paths:
            if path.is_file():
                moved_files += 1
                moved_bytes += path.stat().st_size
    if not moved_files:
        return 0, 0

    archive_destination.mkdir(parents=True, exist_ok=True)
    for child in current_children:
        if child.is_file():
            relative_path = child.relative_to(output_dir)
            destination = archive_destination / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            if relative_path in preserve_relative_paths:
                shutil.copy2(child, destination)
            else:
                shutil.move(str(child), str(destination))
            continue

        for path in sorted(
            (candidate for candidate in child.rglob("*") if candidate.is_file()),
            key=lambda candidate: len(candidate.parts),
        ):
            relative_path = path.relative_to(output_dir)
            destination = archive_destination / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            if relative_path in preserve_relative_paths:
                shutil.copy2(path, destination)
            else:
                shutil.move(str(path), str(destination))

        for directory in sorted(
            (candidate for candidate in child.rglob("*") if candidate.is_dir()),
            key=lambda candidate: len(candidate.parts),
            reverse=True,
        ):
            try:
                directory.rmdir()
            except OSError:
                pass
        try:
            child.rmdir()
        except OSError:
            pass
    return moved_files, moved_bytes


def rotate_previous_outputs(
    qa_root: Path, *, aggregate_only: bool = False,
) -> tuple[int, int, int]:
    """Move the prior generation outside active trees, retaining one generation."""
    scan_roots = [qa_root / "TOTAL_SUMMARY"]
    if not aggregate_only:
        scan_roots.insert(0, qa_root / "STEPS")

    output_dirs: list[Path] = []
    for scan_root in scan_roots:
        if not scan_root.is_dir():
            continue
        for root, dir_names, _ in os.walk(scan_root):
            dir_names[:] = [
                name for name in dir_names
                if name not in {".ATTIC", "__pycache__"}
            ]
            root_path = Path(root)
            if root_path.name == "OUTPUTS":
                output_dirs.append(root_path)

    has_rotatable_files = any(
        path.is_file()
        and not (
            output_dir == qa_root / "TOTAL_SUMMARY" / "OUTPUTS"
            and path.relative_to(output_dir) == REPROCESSING_AUTHORITY_RELATIVE_PATH
        )
        for output_dir in output_dirs
        for path in output_dir.rglob("*")
    )
    if not has_rotatable_files:
        return 0, 0, 0

    archive_root = qa_root / ARCHIVE_ROOT_NAME
    staging_dir = archive_root / ARCHIVE_STAGING_NAME
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)

    rotated_dirs = 0
    moved_files = 0
    moved_bytes = 0
    for output_dir in sorted(output_dirs, key=lambda path: len(path.parts), reverse=True):
        archive_destination = staging_dir / output_dir.relative_to(qa_root)
        preserve_relative_paths = (
            frozenset({REPROCESSING_AUTHORITY_RELATIVE_PATH})
            if output_dir == qa_root / "TOTAL_SUMMARY" / "OUTPUTS"
            else frozenset()
        )
        directory_files, directory_bytes = _rotate_output_directory(
            output_dir,
            archive_destination,
            preserve_relative_paths=preserve_relative_paths,
        )
        if directory_files:
            rotated_dirs += 1
            moved_files += directory_files
            moved_bytes += directory_bytes

    if moved_files:
        previous_dir = archive_root / ARCHIVE_PREVIOUS_NAME
        if previous_dir.exists():
            shutil.rmtree(previous_dir)
        staging_dir.rename(previous_dir)
    else:
        shutil.rmtree(staging_dir)
    return rotated_dirs, moved_files, moved_bytes


def _load_pipeline_steps(qa_root: Path) -> list[dict[str, Any]]:
    config = load_yaml_mapping(qa_root / "config_pipeline.yaml", required=True)
    raw_steps = config.get("steps")
    if not isinstance(raw_steps, list):
        raise ValueError("config_pipeline.yaml must define a 'steps' list.")

    steps: list[dict[str, Any]] = []
    for item in raw_steps:
        if not isinstance(item, dict):
            continue
        step_name = str(item.get("step_name", "")).strip()
        if not step_name:
            continue
        steps.append(
            {
                "order": int(item.get("order", 0)),
                "step_name": step_name,
                "display_name": str(item.get("display_name", step_name)).strip() or step_name,
                "enabled": bool(item.get("enabled", True)),
            }
        )
    return sorted(steps, key=lambda step: (step["order"], step["step_name"]))


def _parse_station_list(values: list[str] | None) -> list[str] | None:
    if not values:
        return None
    return [normalize_station_name(value) for value in values]


def _parse_step_filter(values: list[str] | None) -> set[str] | None:
    if not values:
        return None
    return {str(value).strip() for value in values if str(value).strip()}


def _publish_stage1_product_metadata(
    repo_root: Path,
    root_config: dict[str, Any],
    stations_override: list[str] | None,
) -> tuple[int, int]:
    """Atomically publish lake-authoritative Stage 1 product metadata."""

    raw_stations = stations_override or root_config.get("stations") or []
    station_names = [normalize_station_name(value) for value in raw_stations]
    copied_files = 0
    copied_bytes = 0
    for station_name in station_names:
        station_root = repo_root / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS" / station_name
        lake_dir = station_root / "STAGE_1_PRODUCTS" / "EVENT_DATA" / "PARQUET_LAKE"
        valid_lake_bases = _valid_lake_basenames(lake_dir)
        for task_id in range(6):
            source_dir = station_root / "STAGE_1" / "EVENT_DATA" / "STEP_1" / f"TASK_{task_id}" / "METADATA"
            product_dir = station_root / "STAGE_1_PRODUCTS" / "EVENT_DATA" / "METADATA" / f"TASK_{task_id}"
            if not source_dir.is_dir():
                continue
            product_dir.mkdir(parents=True, exist_ok=True)
            for source_path in sorted(source_dir.glob(f"task_{task_id}_metadata_*.csv")):
                if not source_path.is_file():
                    continue
                lock_path = source_dir / "OPERATION" / f"{source_path.name}.lock"
                lock_path.parent.mkdir(parents=True, exist_ok=True)
                destination_path = product_dir / source_path.name
                with lock_path.open("a", encoding="utf-8") as lock_handle:
                    fcntl.flock(lock_handle.fileno(), fcntl.LOCK_SH)
                    try:
                        changed = _write_lake_gated_metadata(
                            source_path,
                            destination_path,
                            valid_lake_bases,
                        )
                    finally:
                        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
                if not changed:
                    continue
                copied_files += 1
                copied_bytes += destination_path.stat().st_size
    return copied_files, copied_bytes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stations", nargs="*", help="Optional station list like: MINGO01 MINGO02")
    parser.add_argument("--steps", nargs="*", help="Optional step-name filter like: STEP_1_CALIBRATIONS")
    parser.add_argument(
        "--mode",
        choices=("often", "plot", "qa-plot"),
        default="plot",
        help=("Run mode: often updates tables only; plot draws every plottable "
              "parameter; qa-plot draws only quality_and_plot parameters."),
    )
    parser.add_argument("--aggregate-only", action="store_true", help="Only rebuild TOTAL_SUMMARY from existing outputs.")
    parser.add_argument("--skip-total-summary", action="store_true", help="Run steps only.")
    args = parser.parse_args(argv)

    root_config = load_yaml_mapping(QA_ROOT / "config.yaml", required=True)
    pipeline_steps = _load_pipeline_steps(QA_ROOT)
    step_filter = _parse_step_filter(args.steps)
    stations_override = _parse_station_list(args.stations)
    generate_plots = args.mode in {"plot", "qa-plot"}
    quality_plots_only = args.mode == "qa-plot"
    print(
        f"QUALITY_ASSURANCE mode={args.mode} generate_plots={generate_plots} "
        f"plot_scope={'quality_and_plot' if quality_plots_only else 'all_plottable'}"
    )


    if generate_plots:
        rotated_dirs, rotated_files, rotated_bytes = rotate_previous_outputs(
            QA_ROOT,
            aggregate_only=args.aggregate_only,
        )
        print(
            "Archived previous QA outputs outside active OUTPUTS trees: "
            f"directories={rotated_dirs} files={rotated_files} bytes={rotated_bytes}"
        )

    if not args.aggregate_only:
        copied_files, copied_bytes = _publish_stage1_product_metadata(
            REPO_ROOT, root_config, stations_override
        )
        print(
            "Published Stage 1 product metadata for QA: "
            f"files={copied_files} bytes={copied_bytes}"
        )

    if not args.aggregate_only:
        for step in pipeline_steps:
            if not step["enabled"]:
                continue
            if step_filter is not None and step["step_name"] not in step_filter:
                continue
            step_dir = QA_ROOT / "STEPS" / str(step["step_name"])
            run_step(
                step_dir,
                root_config=root_config,
                stations_override=stations_override,
                generate_plots=generate_plots,
                quality_plots_only=quality_plots_only,
            )
    else:
        for step in pipeline_steps:
            if not step["enabled"]:
                continue
            if step_filter is not None and step["step_name"] not in step_filter:
                continue
            step_dir = QA_ROOT / "STEPS" / str(step["step_name"])
            rebuild_step_summaries(
                step_dir,
                root_config=root_config,
                stations_override=stations_override,
            )

    if not args.skip_total_summary:
        build_total_summary(
            QA_ROOT,
            root_config=root_config,
            pipeline_steps=[step for step in pipeline_steps if step_filter is None or step["step_name"] in step_filter],
            stations_override=stations_override,
            generate_plots=generate_plots,
        )
        manifest_path, manifest_df = build_from_file()
        print(f"QA problematic-basename manifest: {manifest_path} ({len(manifest_df)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
