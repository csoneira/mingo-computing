#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY/PLOTTERS/METADATA/EFFICIENCIES_THREE_TO_FOUR/efficiencies_three_to_four_plotter.py
Purpose: Plot per-plane three-to-four trigger efficiencies across STEP_1 tasks.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-30
Runtime: python3
Usage: python3 PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY/PLOTTERS/METADATA/EFFICIENCIES_THREE_TO_FOUR/efficiencies_three_to_four_plotter.py [options]
Inputs: CLI args, config files, and STEP_1 trigger-type metadata.
Outputs: PDF report under PLOTS/.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta
import json
from pathlib import Path
import re
import sys
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages


SCRIPT_PATH = Path(__file__).resolve()


def detect_repo_root() -> Path:
    for parent in SCRIPT_PATH.parents:
        if (parent / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_SCRIPTS").is_dir() and (parent / "CONTEXTUAL" / "CONFIG" / "config_paths.yaml").is_file():
            return parent
    raise RuntimeError(f"Could not locate repository root from {SCRIPT_PATH}")


REPO_ROOT = detect_repo_root()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.plot_utils import pdf_save_rasterized_page  # noqa: E402


STATIONS_ROOT = REPO_ROOT / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS"
PLOTTER_DIR = SCRIPT_PATH.parent
PLOTS_DIR = PLOTTER_DIR / "PLOTS"
DEFAULT_CONFIG_PATH = PLOTTER_DIR / "efficiencies_three_to_four_config.json"
DEFAULT_OUTPUT_FILENAME = "efficiencies_three_to_four_report.pdf"

TASK_IDS: Tuple[int, ...] = (1, 2, 3, 4, 5)
TASK_OUTPUT_TRIGGER_PREFIX: Dict[int, str] = {
    1: "tt_task1_clean",
    2: "tt_task2_cal",
    3: "tt_task3_list",
    4: "tt_task4_fit",
    5: "tt_task5_post",
}
PLANE_TO_MISSING_TRIGGER = {
    1: "234",
    2: "134",
    3: "124",
    4: "123",
}

DEFAULT_EFF_Y_MIN = 0.5
DEFAULT_TAIL_ROWS = 0
DEFAULT_MAX_GAP_HOURS = 3.0

FILENAME_TIMESTAMP_PATTERN = re.compile(r"mi0\d(\d{11})$", re.IGNORECASE)


def configure_matplotlib_style() -> None:
    plt.style.use("default")


def normalize_station_token(token: str) -> Optional[str]:
    cleaned = token.strip().upper()
    if not cleaned:
        return None
    if cleaned.startswith("MINGO"):
        cleaned = cleaned[5:]
    digits = "".join(ch for ch in cleaned if ch.isdigit())
    if not digits:
        return None
    return f"MINGO{int(digits):02d}"


def list_available_stations() -> List[str]:
    if not STATIONS_ROOT.exists():
        return []
    stations: List[str] = []
    for entry in STATIONS_ROOT.iterdir():
        if entry.is_dir() and re.fullmatch(r"MINGO\d{2}", entry.name.upper()):
            stations.append(entry.name.upper())
    stations.sort()
    return stations


def resolve_station_selection(tokens: Sequence[object]) -> List[str]:
    available = list_available_stations()
    if not tokens:
        return [station for station in available if station != "MINGO00"]

    selected: List[str] = []
    skipped: List[str] = []
    for token in tokens:
        station = normalize_station_token(str(token))
        if station is None or station not in available:
            continue
        if station == "MINGO00":
            skipped.append(station)
            continue
        selected.append(station)

    if skipped:
        print(
            "[efficiencies_three_to_four_plotter] Skipping unsupported station(s): "
            + ", ".join(sorted(dict.fromkeys(skipped))),
            file=sys.stderr,
        )

    return sorted(dict.fromkeys(selected))


def normalize_task_selection(values: Sequence[object]) -> List[int]:
    selected: List[int] = []
    for value in values:
        try:
            task_id = int(value)
        except (TypeError, ValueError):
            continue
        if task_id in TASK_IDS:
            selected.append(task_id)
    deduped = sorted(dict.fromkeys(selected))
    return deduped if deduped else list(TASK_IDS)


def normalize_basename(value: object) -> str:
    text = str(value).strip()
    if not text:
        return ""
    return Path(text).stem.strip()


def extract_timestamp_from_basename(value: str) -> Optional[datetime]:
    if not value:
        return None
    stem = Path(value).stem.strip()
    if not stem:
        return None
    try:
        return datetime.strptime(stem, "%Y-%m-%d_%H.%M.%S")
    except ValueError:
        pass

    match = FILENAME_TIMESTAMP_PATTERN.search(stem)
    if match:
        digits = match.group(1)
    else:
        digits = "".join(ch for ch in stem if ch.isdigit())
        if len(digits) < 11:
            return None
        digits = digits[-11:]

    try:
        year = 2000 + int(digits[0:2])
        day_of_year = int(digits[2:5])
        hour = int(digits[5:7])
        minute = int(digits[7:9])
        second = int(digits[9:11])
    except ValueError:
        return None

    if not (1 <= day_of_year <= 366):
        return None

    return datetime(year, 1, 1) + timedelta(
        days=day_of_year - 1,
        hours=hour,
        minutes=minute,
        seconds=second,
    )


def _ordered_unique(values: Iterable[str]) -> List[str]:
    seen: Set[str] = set()
    ordered: List[str] = []
    for value in values:
        candidate = value.strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        ordered.append(candidate)
    return ordered


def _station_token_map(station: str) -> Dict[str, str]:
    clean = station.strip()
    digits = "".join(ch for ch in clean if ch.isdigit())
    stripped = digits.lstrip("0") or "0"
    return {
        "station": clean,
        "station_lower": clean.lower(),
        "id": stripped,
        "id02": stripped.zfill(2),
        "mingo_id": f"mingo{stripped}",
        "mingo_id02": f"mingo{stripped.zfill(2)}",
    }


def _resolve_station_metadata_file(
    directory: Path,
    station: str,
    patterns: Sequence[str],
) -> Optional[Path]:
    tokens = _station_token_map(station)
    for pattern in patterns:
        try:
            candidate = directory / pattern.format(**tokens)
        except KeyError:
            continue
        if candidate.exists():
            return candidate
    return None


def load_allowed_basenames(station: str) -> Set[str]:
    root = STATIONS_ROOT / station
    metadata_dir = root / "STAGE_0" / "REPROCESSING" / "STEP_0" / "OUTPUT_FILES"
    stage0_csv = _resolve_station_metadata_file(
        metadata_dir,
        station,
        (
            "clean_remote_database_{id}.csv",
            "clean_remote_database_{id02}.csv",
            "clean_remote_database_{station_lower}.csv",
            "clean_remote_database_{station}.csv",
            "clean_remote_database_{mingo_id}.csv",
            "clean_remote_database_{mingo_id02}.csv",
        ),
    )
    if stage0_csv is None or not stage0_csv.exists():
        print(
            f"[efficiencies_three_to_four_plotter] Stage 0 basename source missing for {station}.",
            file=sys.stderr,
        )
        return set()

    try:
        df = pd.read_csv(stage0_csv)
    except Exception as exc:  # pragma: no cover
        print(
            f"[efficiencies_three_to_four_plotter] Failed to read {stage0_csv}: {exc}",
            file=sys.stderr,
        )
        return set()

    basename_col = None
    for candidate in ("basename", "filename_base", "hld_name", "dat_name"):
        if candidate in df.columns:
            basename_col = candidate
            break
    if basename_col is None:
        return set()

    return {
        normalize_basename(value)
        for value in df[basename_col].astype(str)
        if normalize_basename(value)
    }


def read_header_columns(path: Path) -> List[str]:
    with path.open("r", encoding="utf-8", errors="ignore", newline="") as handle:
        reader = csv.reader(handle)
        return next(reader, [])


def resolve_usecols(path: Path, task_id: int) -> Optional[List[str]]:
    header_cols = read_header_columns(path)
    if not header_cols:
        return None

    prefix = TASK_OUTPUT_TRIGGER_PREFIX[task_id]
    required = {
        "filename_base",
        "execution_timestamp",
        f"{prefix}_1234_rate_hz",
        f"{prefix}_123_rate_hz",
        f"{prefix}_124_rate_hz",
        f"{prefix}_134_rate_hz",
        f"{prefix}_234_rate_hz",
    }
    return [col for col in header_cols if col in required]


def load_task_metadata(
    station: str,
    task_id: int,
    allowed_basenames: Set[str],
    tail_rows: int,
) -> pd.DataFrame:
    metadata_csv = (
        STATIONS_ROOT
        / station
        / "STAGE_1"
        / "EVENT_DATA"
        / "STEP_1"
        / f"TASK_{task_id}"
        / "METADATA"
        / f"task_{task_id}_metadata_trigger_type.csv"
    )
    if not metadata_csv.exists():
        return pd.DataFrame()

    try:
        usecols = resolve_usecols(metadata_csv, task_id)
        df = pd.read_csv(metadata_csv, usecols=usecols, low_memory=False)
    except Exception as exc:  # pragma: no cover
        print(
            f"[efficiencies_three_to_four_plotter] Failed to read {metadata_csv}: {exc}",
            file=sys.stderr,
        )
        return pd.DataFrame()

    if df.empty or "filename_base" not in df.columns:
        return pd.DataFrame()

    if tail_rows > 0:
        df = df.tail(tail_rows).copy()
    else:
        df = df.copy()

    df["basename"] = df["filename_base"].map(normalize_basename)
    df = df[df["basename"].str.startswith("mi", na=False)]

    if allowed_basenames:
        df = df[df["basename"].isin(allowed_basenames)]
    else:
        df = df.iloc[0:0]

    if df.empty:
        return pd.DataFrame()

    df["file_timestamp"] = pd.to_datetime(
        df["basename"].map(extract_timestamp_from_basename),
        errors="coerce",
    )
    df["execution_dt"] = pd.to_datetime(
        df.get("execution_timestamp"),
        format="%Y-%m-%d_%H.%M.%S",
        errors="coerce",
    )

    prefix = TASK_OUTPUT_TRIGGER_PREFIX[task_id]
    four_plane_col = f"{prefix}_1234_rate_hz"
    for column in (
        four_plane_col,
        f"{prefix}_123_rate_hz",
        f"{prefix}_124_rate_hz",
        f"{prefix}_134_rate_hz",
        f"{prefix}_234_rate_hz",
    ):
        df[column] = pd.to_numeric(df[column], errors="coerce")

    four_plane = df[four_plane_col]
    valid_four_plane = four_plane.where(four_plane > 0)
    for plane, missing_trigger in PLANE_TO_MISSING_TRIGGER.items():
        missing_col = f"{prefix}_{missing_trigger}_rate_hz"
        df[f"eff_p{plane}"] = 1.0 - (df[missing_col] / valid_four_plane)

    df = df[df["file_timestamp"].notna()].copy()
    if df.empty:
        return pd.DataFrame()

    df = df.sort_values(["basename", "execution_dt", "file_timestamp"])
    df = df.drop_duplicates(subset=["basename"], keep="last")
    df["task"] = task_id
    return df.sort_values("file_timestamp").reset_index(drop=True)


def station_time_bounds(task_data: Dict[int, pd.DataFrame]) -> Optional[Tuple[pd.Timestamp, pd.Timestamp]]:
    chunks: List[pd.Series] = []
    for df in task_data.values():
        if df.empty:
            continue
        chunks.append(pd.to_datetime(df["file_timestamp"], errors="coerce"))

    if not chunks:
        return None

    combined = pd.concat(chunks, ignore_index=True).dropna()
    if combined.empty:
        return None

    lower = pd.Timestamp(combined.min())
    upper = pd.Timestamp(combined.max())
    if lower == upper:
        upper = lower + timedelta(minutes=1)
    return lower, upper


def build_task_color_map(tasks: Sequence[int]) -> Dict[int, tuple]:
    cmap = plt.get_cmap("tab10")
    return {
        task_id: cmap(idx % cmap.N)
        for idx, task_id in enumerate(tasks)
    }


def _plot_gap_aware_line(
    ax: plt.Axes,
    x_values: pd.Series,
    y_values: pd.Series,
    *,
    color: tuple,
    label: str,
    max_gap_hours: float,
) -> None:
    df = pd.DataFrame({"x": x_values, "y": y_values}).dropna(subset=["x", "y"]).copy()
    if df.empty:
        return

    df = df.sort_values("x")
    if len(df) == 1 or not np.isfinite(max_gap_hours) or max_gap_hours <= 0:
        ax.plot(df["x"], df["y"], color=color, linewidth=1.2, label=label)
        return

    segments: List[pd.DataFrame] = []
    start_idx = 0
    timestamps = pd.to_datetime(df["x"]).reset_index(drop=True)
    for idx in range(1, len(df)):
        gap_hours = (timestamps.iloc[idx] - timestamps.iloc[idx - 1]).total_seconds() / 3600.0
        if gap_hours > max_gap_hours:
            segments.append(df.iloc[start_idx:idx])
            start_idx = idx
    segments.append(df.iloc[start_idx:])

    first = True
    for segment in segments:
        if segment.empty:
            continue
        ax.plot(
            segment["x"],
            segment["y"],
            color=color,
            linewidth=1.2,
            label=label if first else None,
        )
        first = False


def plot_plane_axis(
    ax: plt.Axes,
    *,
    plane: int,
    task_data: Dict[int, pd.DataFrame],
    tasks: Sequence[int],
    task_colors: Dict[int, tuple],
    eff_y_min: float,
    x_limits: Optional[Tuple[pd.Timestamp, pd.Timestamp]],
    max_gap_hours: float,
) -> None:
    missing_trigger = PLANE_TO_MISSING_TRIGGER[plane]
    ax.set_title(
        f"Plane P{plane}: 1 - N{missing_trigger} / N1234",
        fontsize=10,
    )
    ax.set_ylabel("Efficiency")
    ax.set_ylim(eff_y_min, 1.0)
    ax.grid(True, axis="y", alpha=0.3, linestyle="--", linewidth=0.5)

    if x_limits is not None:
        ax.set_xlim(x_limits[0], x_limits[1])

    plotted = False
    for task_id in tasks:
        df = task_data.get(task_id, pd.DataFrame())
        if df.empty:
            continue

        eff_col = f"eff_p{plane}"
        if eff_col not in df.columns:
            continue

        plot_df = df[["file_timestamp", eff_col]].copy()
        plot_df[eff_col] = pd.to_numeric(plot_df[eff_col], errors="coerce")
        plot_df = plot_df.dropna(subset=["file_timestamp", eff_col])
        if plot_df.empty:
            continue

        color = task_colors[task_id]
        _plot_gap_aware_line(
            ax,
            plot_df["file_timestamp"],
            plot_df[eff_col],
            color=color,
            label=f"Task {task_id}",
            max_gap_hours=max_gap_hours,
        )
        ax.scatter(
            plot_df["file_timestamp"],
            plot_df[eff_col],
            s=10,
            color=color,
            alpha=0.8,
        )
        plotted = True

    if not plotted:
        ax.text(
            0.5,
            0.5,
            "No eligible rows",
            transform=ax.transAxes,
            ha="center",
            va="center",
            fontsize=9,
            color="dimgray",
        )


def plot_station_page(
    station: str,
    task_data: Dict[int, pd.DataFrame],
    tasks: Sequence[int],
    pdf: PdfPages,
    *,
    eff_y_min: float,
    max_gap_hours: float,
    allowed_count: int,
) -> None:
    fig, axes = plt.subplots(
        4,
        1,
        figsize=(16, 11),
        sharex=True,
        sharey=True,
        constrained_layout=True,
    )

    x_limits = station_time_bounds(task_data)
    task_colors = build_task_color_map(tasks)

    fig.suptitle(
        f"{station} - Three-to-Four Estimated Efficiencies\n"
        f"Eligible basenames from Stage 0: {allowed_count}",
        fontsize=13,
    )

    for plane, ax in enumerate(np.atleast_1d(axes), start=1):
        plot_plane_axis(
            ax,
            plane=plane,
            task_data=task_data,
            tasks=tasks,
            task_colors=task_colors,
            eff_y_min=eff_y_min,
            x_limits=x_limits,
            max_gap_hours=max_gap_hours,
        )

    locator = mdates.AutoDateLocator(minticks=4, maxticks=10)
    formatter = mdates.ConciseDateFormatter(locator)
    axes[-1].xaxis.set_major_locator(locator)
    axes[-1].xaxis.set_major_formatter(formatter)
    axes[-1].set_xlabel("Basename timestamp")

    handles, labels = axes[0].get_legend_handles_labels()
    if handles:
        axes[0].legend(handles, labels, loc="upper left", ncols=min(len(handles), 5), fontsize=8)

    pdf_save_rasterized_page(pdf, fig)
    plt.close(fig)


def load_config(config_path: Path) -> Dict[str, object]:
    if not config_path.exists():
        return {}
    with config_path.open("r", encoding="utf-8") as handle:
        loaded = json.load(handle)
    return loaded if isinstance(loaded, dict) else {}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot three-to-four per-plane efficiencies from trigger metadata.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help=f"Path to JSON config (default: {DEFAULT_CONFIG_PATH})",
    )
    parser.add_argument(
        "--stations",
        nargs="*",
        default=None,
        help="Optional station selection override (e.g. 1 2 or MINGO01).",
    )
    parser.add_argument(
        "--tasks",
        nargs="*",
        default=None,
        help="Optional task selection override.",
    )
    return parser.parse_args()


def main() -> None:
    configure_matplotlib_style()
    args = parse_args()
    config_path = args.config.resolve()
    config = load_config(config_path)

    if args.stations is not None:
        stations = resolve_station_selection(args.stations)
    else:
        stations = resolve_station_selection(config.get("stations", []))

    if args.tasks is not None:
        tasks = normalize_task_selection(args.tasks)
    else:
        tasks = normalize_task_selection(config.get("tasks", TASK_IDS))

    eff_y_min = float(config.get("eff_y_min", DEFAULT_EFF_Y_MIN))
    tail_rows = int(config.get("tail_rows", DEFAULT_TAIL_ROWS) or 0)
    max_gap_hours = float(config.get("max_gap_hours", DEFAULT_MAX_GAP_HOURS))

    output_value = str(config.get("output", DEFAULT_OUTPUT_FILENAME)).strip() or DEFAULT_OUTPUT_FILENAME
    output_path = Path(output_value)
    if not output_path.is_absolute():
        output_path = (config_path.parent / output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not stations:
        print("[efficiencies_three_to_four_plotter] No eligible stations selected.", file=sys.stderr)
        return

    with PdfPages(output_path) as pdf:
        plotted_any = False
        for station in stations:
            allowed_basenames = load_allowed_basenames(station)
            task_data: Dict[int, pd.DataFrame] = {}
            for task_id in tasks:
                task_data[task_id] = load_task_metadata(
                    station=station,
                    task_id=task_id,
                    allowed_basenames=allowed_basenames,
                    tail_rows=tail_rows,
                )

            if not any(not df.empty for df in task_data.values()):
                print(
                    f"[efficiencies_three_to_four_plotter] No eligible rows for {station}.",
                    file=sys.stderr,
                )
                continue

            plot_station_page(
                station,
                task_data,
                tasks,
                pdf,
                eff_y_min=eff_y_min,
                max_gap_hours=max_gap_hours,
                allowed_count=len(allowed_basenames),
            )
            plotted_any = True

        if not plotted_any:
            fig, ax = plt.subplots(figsize=(11, 4))
            ax.axis("off")
            ax.text(
                0.5,
                0.5,
                "No eligible metadata rows found.",
                ha="center",
                va="center",
                fontsize=12,
                color="dimgray",
                transform=ax.transAxes,
            )
            pdf_save_rasterized_page(pdf, fig)
            plt.close(fig)

    print(f"[efficiencies_three_to_four_plotter] Saved report to {output_path}")


if __name__ == "__main__":
    main()
