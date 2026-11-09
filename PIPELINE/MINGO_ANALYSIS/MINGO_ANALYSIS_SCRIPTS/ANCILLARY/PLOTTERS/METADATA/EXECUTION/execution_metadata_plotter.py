#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY/PLOTTERS/METADATA/EXECUTION/execution_metadata_plotter.py
Purpose: Execution-metadata plotter: Tasks 1-5 overlaid (execution time only).
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY/PLOTTERS/METADATA/EXECUTION/execution_metadata_plotter.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import json
from pathlib import Path
import re
import sys
from typing import Dict, List, Optional, Sequence, Set, Tuple

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
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
DEFAULT_CONFIG_PATH = PLOTTER_DIR / "execution_metadata_config.json"
DEFAULT_OUTPUT_FILENAME = "execution_metadata_report.pdf"

TASK_IDS: Tuple[int, ...] = (1, 2, 3, 4, 5)
DEFAULT_Y_MIN_MINUTES = 0.0
DEFAULT_Y_MAX_MINUTES = 5.0
DEFAULT_MARKER_SIZE = 14.0
DEFAULT_LAST_HOURS = 2.0
DEFAULT_PANEL_WIDTH_RATIOS: Tuple[float, float, float] = (4.0, 1.0, 1.2)
VELOCITY_WINDOW_HOURS = 1.0
NOW_X_MARGIN_MINUTES = 10.0

BASENAME_TIMESTAMP_DIGITS = 11
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


def resolve_station_selection(tokens: Sequence[str]) -> List[str]:
    available = list_available_stations()
    if not tokens:
        return available

    selected: List[str] = []
    invalid: List[str] = []
    for token in tokens:
        station = normalize_station_token(str(token))
        if station is None or station not in available:
            invalid.append(str(token))
            continue
        selected.append(station)

    if invalid:
        print(
            "[execution_metadata_plotter] Ignoring unknown station(s): "
            + ", ".join(invalid),
            file=sys.stderr,
        )

    return sorted(dict.fromkeys(selected))


def normalize_existing_station_tokens(tokens: Sequence[object]) -> List[str]:
    available = set(list_available_stations())
    selected: List[str] = []
    for token in tokens:
        station = normalize_station_token(str(token))
        if station is None or station not in available:
            continue
        selected.append(station)
    return sorted(dict.fromkeys(selected))


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
        if len(digits) < BASENAME_TIMESTAMP_DIGITS:
            return None
        digits = digits[-BASENAME_TIMESTAMP_DIGITS:]

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
    if not (0 <= hour <= 23):
        return None
    if not (0 <= minute <= 59):
        return None
    if not (0 <= second <= 59):
        return None

    base = datetime(year, 1, 1)
    return base + timedelta(
        days=day_of_year - 1,
        hours=hour,
        minutes=minute,
        seconds=second,
    )


def parse_execution_series(series: pd.Series) -> pd.Series:
    text = series.astype(str).str.strip()
    parsed = pd.to_datetime(text, format="%Y-%m-%d_%H.%M.%S", errors="coerce")
    missing = parsed.isna()
    if missing.any():
        parsed.loc[missing] = pd.to_datetime(text[missing], errors="coerce")
    return parsed


def now_like(reference: pd.Timestamp) -> pd.Timestamp:
    reference_ts = pd.Timestamp(reference)
    now_utc = pd.Timestamp.utcnow()
    if reference_ts.tzinfo is None:
        return now_utc.tz_localize(None)
    return now_utc.tz_convert(reference_ts.tzinfo)


def _ordered_unique(values: Sequence[str]) -> List[str]:
    seen: Set[str] = set()
    ordered: List[str] = []
    for value in values:
        candidate = str(value).strip()
        if not candidate or candidate in seen:
            continue
        ordered.append(candidate)
        seen.add(candidate)
    return ordered


def _station_token_map(station: str) -> Dict[str, str]:
    clean = station.strip()
    tokens: Dict[str, str] = {
        "station": clean,
        "station_lower": clean.lower(),
        "station_upper": clean.upper(),
    }
    digits = "".join(ch for ch in clean if ch.isdigit())
    if digits:
        stripped = digits.lstrip("0") or "0"
        tokens["id"] = stripped
        tokens["id02"] = stripped.zfill(2)
        tokens["mingo_id"] = f"mingo{stripped}"
        tokens["mingo_id02"] = f"mingo{tokens['id02']}"
    return tokens


def _resolve_station_metadata_file(
    directory: Path,
    station: str,
    patterns: Sequence[str],
) -> Optional[Path]:
    tokens = _station_token_map(station)
    candidates: List[str] = []
    for pattern in patterns:
        try:
            candidates.append(pattern.format(**tokens))
        except KeyError:
            continue

    for filename in _ordered_unique(candidates):
        candidate = directory / filename
        if candidate.exists():
            return candidate
    return None


def load_allowed_basenames(station: str) -> Set[str]:
    root = STATIONS_ROOT / station

    if station == "MINGO00":
        stage0_history_csv = root / "STAGE_0" / "SIMULATION" / "imported_basenames_history.csv"
        stage0_live_csv = root / "STAGE_0" / "SIMULATION" / "imported_basenames.csv"
        stage0_csv = stage0_history_csv if stage0_history_csv.exists() else stage0_live_csv
    else:
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
            f"[execution_metadata_plotter] Stage 0 basename source missing for {station}.",
            file=sys.stderr,
        )
        return set()

    try:
        df = pd.read_csv(stage0_csv)
    except Exception as exc:  # pragma: no cover - defensive
        print(
            f"[execution_metadata_plotter] Failed to read {stage0_csv}: {exc}",
            file=sys.stderr,
        )
        return set()

    basename_col = None
    for candidate in ("basename", "filename_base", "hld_name", "dat_name"):
        if candidate in df.columns:
            basename_col = candidate
            break

    if basename_col is None:
        print(
            f"[execution_metadata_plotter] Missing basename column in {stage0_csv}.",
            file=sys.stderr,
        )
        return set()

    return {
        normalize_basename(value)
        for value in df[basename_col].astype(str)
        if normalize_basename(value)
    }


def load_task_execution_data(station: str, task_id: int, allowed_basenames: Set[str]) -> pd.DataFrame:
    metadata_csv = (
        STATIONS_ROOT
        / station
        / "STAGE_1"
        / "EVENT_DATA"
        / "STEP_1"
        / f"TASK_{task_id}"
        / "METADATA"
        / f"task_{task_id}_metadata_execution.csv"
    )
    if not metadata_csv.exists():
        return pd.DataFrame()

    try:
        df = pd.read_csv(
            metadata_csv,
            usecols=["filename_base", "execution_timestamp", "total_execution_time_minutes"],
            low_memory=False,
        )
    except Exception as exc:  # pragma: no cover - defensive
        print(
            f"[execution_metadata_plotter] Failed to read {metadata_csv}: {exc}",
            file=sys.stderr,
        )
        return pd.DataFrame()

    if df.empty or "filename_base" not in df.columns:
        return pd.DataFrame()

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
    df["execution_timestamp"] = parse_execution_series(df["execution_timestamp"])
    df["total_execution_time_minutes"] = pd.to_numeric(
        df["total_execution_time_minutes"],
        errors="coerce",
    )

    df = df.dropna(subset=["file_timestamp", "total_execution_time_minutes"])
    if df.empty:
        return pd.DataFrame()

    df = df.drop_duplicates(subset=["basename"], keep="last")
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


def station_execution_last_window(
    task_data: Dict[int, pd.DataFrame],
    last_hours: float,
) -> Optional[Tuple[pd.Timestamp, pd.Timestamp]]:
    chunks: List[pd.Series] = []
    for df in task_data.values():
        if df.empty or "execution_timestamp" not in df.columns:
            continue
        chunks.append(pd.to_datetime(df["execution_timestamp"], errors="coerce"))

    if not chunks:
        return None

    combined = pd.concat(chunks, ignore_index=True).dropna()
    if combined.empty:
        return None

    reference_upper = pd.Timestamp(combined.max())
    now = now_like(reference_upper)
    upper = now + timedelta(minutes=NOW_X_MARGIN_MINUTES)
    lower = now - timedelta(hours=last_hours)
    if lower == upper:
        lower = upper - timedelta(minutes=1)
    return lower, upper


def build_velocity_series(task_data: Dict[int, pd.DataFrame]) -> pd.DataFrame:
    chunks: List[pd.Series] = []
    for df in task_data.values():
        if df.empty or "execution_timestamp" not in df.columns:
            continue
        chunks.append(pd.to_datetime(df["execution_timestamp"], errors="coerce"))

    if not chunks:
        return pd.DataFrame(columns=["execution_timestamp", "files_per_hour"])

    combined = pd.concat(chunks, ignore_index=True).dropna()
    if combined.empty:
        return pd.DataFrame(columns=["execution_timestamp", "files_per_hour"])

    events = pd.DataFrame({"execution_timestamp": pd.to_datetime(combined)})
    events["count"] = 1
    grouped = events.groupby("execution_timestamp", as_index=False, sort=True)["count"].sum()
    grouped = grouped.sort_values("execution_timestamp")
    indexed = grouped.set_index("execution_timestamp")
    rolling_counts = indexed["count"].rolling(pd.Timedelta(hours=VELOCITY_WINDOW_HOURS)).sum()

    return rolling_counts.rename("files_per_hour").reset_index()


def plot_station_page(
    station: str,
    task_data: Dict[int, pd.DataFrame],
    pdf: PdfPages,
    y_min_minutes: float,
    y_max_minutes: float,
    marker_size: float,
    last_hours: float,
    panel_width_ratios: Tuple[float, float, float],
    allowed_count: int,
) -> None:
    fig, axes = plt.subplots(
        1,
        3,
        figsize=(18, 6),
        constrained_layout=True,
        gridspec_kw={"width_ratios": panel_width_ratios},
    )
    left_ax, middle_ax, right_ax = axes
    fig.suptitle(
        (
            f"{station} - Execution time + velocity "
            f"(Tasks 1-5, clean_remote/imported basenames: {allowed_count})"
        ),
        fontsize=13,
    )

    left_limits = station_time_bounds(task_data)
    middle_and_right_limits = station_execution_last_window(task_data, last_hours)
    velocity_series = build_velocity_series(task_data)

    cmap = plt.get_cmap("tab10")

    def _plot_overlay(
        ax: plt.Axes,
        x_col: str,
        title: str,
        x_limits: Optional[Tuple[pd.Timestamp, pd.Timestamp]],
        right_window_only: bool = False,
    ) -> bool:
        ax.set_title(title, fontsize=10)
        ax.set_ylabel("Execution time (minutes)")
        ax.set_ylim(y_min_minutes, y_max_minutes)
        ax.grid(True, axis="y", alpha=0.3, linestyle="--", linewidth=0.5)
        if x_limits is not None:
            ax.set_xlim(x_limits[0], x_limits[1])

        plotted_local = False
        for idx, task_id in enumerate(TASK_IDS):
            df = task_data.get(task_id, pd.DataFrame())
            if df.empty or x_col not in df.columns:
                continue

            task_df = df.dropna(subset=[x_col, "total_execution_time_minutes"]).copy()
            if task_df.empty:
                continue

            if right_window_only and x_limits is not None:
                low, high = x_limits
                task_df = task_df[
                    (task_df[x_col] >= low)
                    & (task_df[x_col] <= high)
                ]
                if task_df.empty:
                    continue

            task_df = task_df.sort_values(x_col)
            color = cmap(idx % cmap.N)
            ax.plot(
                task_df[x_col],
                task_df["total_execution_time_minutes"],
                linewidth=1.2,
                color=color,
                label=f"Task {task_id}",
            )
            ax.scatter(
                task_df[x_col],
                task_df["total_execution_time_minutes"],
                s=marker_size,
                color=color,
                alpha=0.85,
            )
            plotted_local = True

        if x_col == "execution_timestamp" and x_limits is not None:
            now = now_like(pd.Timestamp(x_limits[1]))
            ax.axvline(now, color="red", linestyle="--", alpha=0.3, zorder=10)

        if not plotted_local:
            ax.text(
                0.5,
                0.5,
                "No eligible rows",
                transform=ax.transAxes,
                ha="center",
                va="center",
                fontsize=10,
                color="dimgray",
            )
        return plotted_local

    left_plotted = _plot_overlay(
        ax=left_ax,
        x_col="file_timestamp",
        title="Tasks 1-5 - Basename timestamp",
        x_limits=left_limits,
        right_window_only=False,
    )
    middle_plotted = _plot_overlay(
        ax=middle_ax,
        x_col="execution_timestamp",
        title=f"Tasks 1-5 - Exec. time (last {last_hours:g}h from now UTC)",
        x_limits=middle_and_right_limits,
        right_window_only=True,
    )

    right_ax.set_title(
        f"Velocity (files/hour, trailing {VELOCITY_WINDOW_HOURS:g}h)",
        fontsize=10,
    )
    right_ax.set_ylabel("Files / hour")
    right_ax.grid(True, axis="y", alpha=0.3, linestyle="--", linewidth=0.5)
    if middle_and_right_limits is not None:
        right_ax.set_xlim(middle_and_right_limits[0], middle_and_right_limits[1])

    velocity_plotted = False
    if not velocity_series.empty:
        velocity_df = velocity_series.copy()
        if middle_and_right_limits is not None:
            low, high = middle_and_right_limits
            velocity_df = velocity_df[
                (velocity_df["execution_timestamp"] >= low)
                & (velocity_df["execution_timestamp"] <= high)
            ]
        if not velocity_df.empty:
            right_ax.plot(
                velocity_df["execution_timestamp"],
                velocity_df["files_per_hour"],
                linewidth=1.6,
                color="#1f77b4",
            )
            right_ax.scatter(
                velocity_df["execution_timestamp"],
                velocity_df["files_per_hour"],
                s=max(marker_size * 0.8, 10.0),
                color="#1f77b4",
                alpha=0.85,
            )
            max_velocity = float(velocity_df["files_per_hour"].max())
            right_ax.set_ylim(0.0, max(1.0, max_velocity * 1.15))
            velocity_plotted = True

    if middle_and_right_limits is not None:
        now = now_like(pd.Timestamp(middle_and_right_limits[1]))
        right_ax.axvline(now, color="red", linestyle="--", alpha=0.3, zorder=10)

    if not velocity_plotted:
        right_ax.set_ylim(0.0, 1.0)
        right_ax.text(
            0.5,
            0.5,
            "No eligible rows",
            transform=right_ax.transAxes,
            ha="center",
            va="center",
            fontsize=10,
            color="dimgray",
        )

    if left_plotted:
        left_ax.legend(loc="upper left", ncols=3, fontsize=8)
    elif middle_plotted:
        middle_ax.legend(loc="upper left", ncols=2, fontsize=8)

    left_ax.set_xlabel("Basename timestamp")
    middle_ax.set_xlabel("Execution timestamp")
    right_ax.set_xlabel("Execution timestamp")
    left_ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d\n%H:%M"))
    middle_ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    right_ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    middle_ax.tick_params(axis="x", labelrotation=45)
    right_ax.tick_params(axis="x", labelrotation=45)
    for tick in middle_ax.get_xticklabels():
        tick.set_horizontalalignment("right")
    for tick in right_ax.get_xticklabels():
        tick.set_horizontalalignment("right")

    pdf_save_rasterized_page(pdf, fig, dpi=150)
    plt.close(fig)


def default_output_path() -> Path:
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    return PLOTS_DIR / DEFAULT_OUTPUT_FILENAME


def load_config(config_path: Path) -> Dict[str, object]:
    if not config_path.exists():
        return {}

    try:
        with config_path.open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
    except Exception as exc:  # pragma: no cover - defensive
        raise ValueError(f"Failed to parse config JSON {config_path}: {exc}") from exc

    if not isinstance(loaded, dict):
        raise ValueError(f"Config file must contain a JSON object: {config_path}")
    return loaded


def resolve_output_path(raw_output: Optional[str], config_path: Path) -> Path:
    if not raw_output:
        return default_output_path()
    candidate = Path(raw_output).expanduser()
    if candidate.is_absolute():
        return candidate
    return (config_path.parent / candidate).resolve()


def resolve_runtime_options(
    args: argparse.Namespace,
) -> Tuple[List[str], float, float, float, float, Tuple[float, float, float], Path]:
    config_path = Path(args.config).expanduser()
    config = load_config(config_path)

    if args.stations is not None:
        stations = resolve_station_selection(args.stations)
    else:
        cfg_stations = config.get("stations", [])
        if not isinstance(cfg_stations, list):
            raise ValueError("'stations' in config must be a list")
        normalized = normalize_existing_station_tokens(cfg_stations)
        stations = normalized if normalized else list_available_stations()

    try:
        y_min_minutes = float(config.get("y_min_minutes", DEFAULT_Y_MIN_MINUTES))
        y_max_minutes = float(config.get("y_max_minutes", DEFAULT_Y_MAX_MINUTES))
    except (TypeError, ValueError):
        raise ValueError("'y_min_minutes' and 'y_max_minutes' in config must be numeric")
    if y_max_minutes <= y_min_minutes:
        raise ValueError("'y_max_minutes' must be > 'y_min_minutes'")

    try:
        marker_size = float(config.get("marker_size", DEFAULT_MARKER_SIZE))
    except (TypeError, ValueError):
        raise ValueError("'marker_size' in config must be numeric")
    if marker_size <= 0:
        raise ValueError("'marker_size' must be > 0")

    try:
        last_hours = float(config.get("last_hours", DEFAULT_LAST_HOURS))
    except (TypeError, ValueError):
        raise ValueError("'last_hours' in config must be numeric")
    if last_hours <= 0:
        raise ValueError("'last_hours' must be > 0")

    panel_width_raw = config.get("panel_width_ratios", list(DEFAULT_PANEL_WIDTH_RATIOS))
    if not isinstance(panel_width_raw, list) or len(panel_width_raw) not in (2, 3):
        raise ValueError(
            "'panel_width_ratios' in config must be a list of 2 or 3 numeric values"
        )
    try:
        panel_values = [float(value) for value in panel_width_raw]
    except (TypeError, ValueError):
        raise ValueError("'panel_width_ratios' in config must contain numeric values")
    if any(value <= 0 for value in panel_values):
        raise ValueError("'panel_width_ratios' values must be > 0")

    if len(panel_values) == 2:
        panel_width_ratios = (
            panel_values[0],
            panel_values[1],
            max(panel_values[1], 1.0),
        )
    else:
        panel_width_ratios = (panel_values[0], panel_values[1], panel_values[2])

    output_raw = args.output
    if output_raw is None:
        config_output = config.get("output")
        output_raw = str(config_output) if config_output is not None else None
    output_path = resolve_output_path(output_raw, config_path)

    return (
        stations,
        y_min_minutes,
        y_max_minutes,
        marker_size,
        last_hours,
        panel_width_ratios,
        output_path,
    )


def ensure_output_directory(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate execution-time metadata report (Tasks 1-5 overlaid, clean_remote/imported only)."
        )
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help=f"Path to JSON config (default: {DEFAULT_CONFIG_PATH}).",
    )
    parser.add_argument(
        "--stations",
        nargs="+",
        default=None,
        help="Station selection override (e.g. MINGO00 MINGO01).",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output PDF path override (absolute or config-relative).",
    )
    return parser


def main() -> None:
    configure_matplotlib_style()
    args = build_parser().parse_args()

    (
        stations,
        y_min_minutes,
        y_max_minutes,
        marker_size,
        last_hours,
        panel_width_ratios,
        output_path,
    ) = resolve_runtime_options(args)

    if not stations:
        raise RuntimeError("No stations selected or discovered.")

    ensure_output_directory(output_path)

    with PdfPages(output_path) as pdf:
        for station in stations:
            allowed_basenames = load_allowed_basenames(station)
            task_data: Dict[int, pd.DataFrame] = {}
            for task_id in TASK_IDS:
                task_data[task_id] = load_task_execution_data(
                    station=station,
                    task_id=task_id,
                    allowed_basenames=allowed_basenames,
                )

            plot_station_page(
                station=station,
                task_data=task_data,
                pdf=pdf,
                y_min_minutes=y_min_minutes,
                y_max_minutes=y_max_minutes,
                marker_size=marker_size,
                last_hours=last_hours,
                panel_width_ratios=panel_width_ratios,
                allowed_count=len(allowed_basenames),
            )

    print(f"Saved execution metadata report: {output_path}")


if __name__ == "__main__":
    main()
