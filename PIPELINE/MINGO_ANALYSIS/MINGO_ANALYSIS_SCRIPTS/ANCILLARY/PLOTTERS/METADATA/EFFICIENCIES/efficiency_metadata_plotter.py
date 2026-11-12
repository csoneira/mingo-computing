#!/usr/bin/env python3

"""Plot Task 4 efficiency-vs-X/Y/theta metadata as time heatmaps."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta
import json
from pathlib import Path
import re
import sys
from typing import Iterable, List, Optional, Sequence, Set, Tuple

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages


SCRIPT_PATH = Path(__file__).resolve()


_REPO_IMPORT_ROOT = SCRIPT_PATH.parents[7]
if str(_REPO_IMPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_IMPORT_ROOT))
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.path_config import get_repo_root

REPO_ROOT = get_repo_root()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.plot_utils import pdf_save_rasterized_page  # noqa: E402


STATIONS_ROOT = REPO_ROOT / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS"
PLOTTER_DIR = SCRIPT_PATH.parent
PLOTS_DIR = PLOTTER_DIR / "PLOTS"
DEFAULT_CONFIG_PATH = PLOTTER_DIR / "efficiency_metadata_config.json"
DEFAULT_OUTPUT_FILENAME = "efficiency_metadata_report.pdf"
DEFAULT_TASK_ID = 4
DEFAULT_EFF_LIM = 0.50
DEFAULT_TAIL_ROWS = 0
DEFAULT_MAX_BIN_GAP_HOURS = 3.0
FILENAME_TIMESTAMP_PATTERN = re.compile(r"mi0\d(\d{11})$", re.IGNORECASE)
EFFICIENCY_VECTOR_COL_RE = re.compile(
    r"^efficiency_vector_p(?P<plane>[1-4])_(?P<axis>x|y|theta)_bin_(?P<bin>\d+)_(?P<field>center_mm|center_deg|eff|unc)$"
)
AXIS_ORDER: Tuple[str, ...] = ("x", "y", "theta")
AXIS_LABELS = {
    "x": "Projected X (mm)",
    "y": "Projected Y (mm)",
    "theta": "Theta (deg)",
}


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
        return available
    selected: List[str] = []
    for token in tokens:
        station = normalize_station_token(str(token))
        if station and station in available:
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
    base = datetime(year, 1, 1)
    return base + timedelta(
        days=day_of_year - 1,
        hours=hour,
        minutes=minute,
        seconds=second,
    )


def _ordered_unique(values: Iterable[str]) -> List[str]:
    seen: Set[str] = set()
    ordered: List[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered


def _station_token_map(station: str) -> dict[str, str]:
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
        print(f"[efficiency_metadata_plotter] Stage 0 basename source missing for {station}.", file=sys.stderr)
        return set()
    try:
        df = pd.read_csv(stage0_csv)
    except Exception as exc:  # pragma: no cover
        print(f"[efficiency_metadata_plotter] Failed to read {stage0_csv}: {exc}", file=sys.stderr)
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


def resolve_usecols(path: Path) -> Optional[List[str]]:
    header_cols = read_header_columns(path)
    if not header_cols:
        return None
    required = {
        "filename_base",
        "execution_timestamp",
        "efficiency_metadata_available",
        "efficiency_metadata_reason",
    }
    for col in header_cols:
        if EFFICIENCY_VECTOR_COL_RE.match(str(col)):
            required.add(str(col))
        elif str(col).startswith("efficiency_vector_p") and (
            str(col).endswith("_overall_eff_percent") or str(col).endswith("_n_denom")
        ):
            required.add(str(col))
    return [col for col in header_cols if col in required]


def load_efficiency_metadata(
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
        / f"task_{task_id}_metadata_efficiency.csv"
    )
    if not metadata_csv.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(metadata_csv, usecols=resolve_usecols(metadata_csv), low_memory=False)
    except Exception as exc:  # pragma: no cover
        print(f"[efficiency_metadata_plotter] Failed to read {metadata_csv}: {exc}", file=sys.stderr)
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
    if "efficiency_metadata_available" in df.columns:
        available = pd.to_numeric(df["efficiency_metadata_available"], errors="coerce").fillna(0).astype(bool)
        df = df.loc[available].copy()
    df = df[df["file_timestamp"].notna()].copy()
    if df.empty:
        return pd.DataFrame()
    df = df.drop_duplicates(subset=["basename"], keep="last")
    return df.sort_values("file_timestamp").reset_index(drop=True)


def build_intervalized_matrix(
    times_num: np.ndarray,
    value_matrix: np.ndarray,
    max_bin_gap_hours: float,
    fallback_seconds: float,
) -> Tuple[np.ndarray, np.ndarray]:
    if times_num.size == 0:
        return np.array([], dtype=float), np.empty((value_matrix.shape[0], 0), dtype=float)
    fallback_days = max(float(fallback_seconds), 1.0) / 86400.0
    diffs = np.diff(times_num)
    positive_diffs = diffs[diffs > 0]
    tail_days = float(np.median(positive_diffs)) if positive_diffs.size > 0 else fallback_days
    max_gap_days = max(float(max_bin_gap_hours), 1.0 / 3600.0) / 24.0 if np.isfinite(max_bin_gap_hours) else np.inf
    tail_days = min(tail_days, max_gap_days) if np.isfinite(max_gap_days) else tail_days

    intervals: List[Tuple[float, float, Optional[int]]] = []
    for idx, start in enumerate(times_num):
        start_v = float(start)
        if idx < times_num.size - 1:
            next_v = float(times_num[idx + 1])
            end_v = min(next_v, start_v + max_gap_days) if np.isfinite(max_gap_days) else next_v
        else:
            end_v = start_v + max(tail_days, fallback_days / 2.0)
        if end_v <= start_v:
            end_v = start_v + fallback_days / 2.0
        intervals.append((start_v, end_v, idx))
        if idx < times_num.size - 1:
            next_v = float(times_num[idx + 1])
            if end_v < next_v:
                intervals.append((end_v, next_v, None))

    x_edges = np.empty(len(intervals) + 1, dtype=float)
    plot_matrix = np.empty((value_matrix.shape[0], len(intervals)), dtype=float)
    x_edges[0] = intervals[0][0]
    for col_idx, (_start_v, end_v, src_idx) in enumerate(intervals):
        x_edges[col_idx + 1] = end_v
        if src_idx is None:
            plot_matrix[:, col_idx] = np.nan
        else:
            plot_matrix[:, col_idx] = value_matrix[:, src_idx]
    return x_edges, plot_matrix


def compute_axis_edges(centers: np.ndarray, fallback_width: float) -> np.ndarray:
    vals = np.asarray(centers, dtype=float)
    if vals.size == 0:
        return np.array([], dtype=float)
    if vals.size == 1:
        half = max(float(fallback_width) / 2.0, 1e-6)
        return np.array([vals[0] - half, vals[0] + half], dtype=float)
    diffs = np.diff(vals)
    positive = diffs[np.isfinite(diffs) & (diffs > 0)]
    delta = float(np.median(positive)) if positive.size > 0 else max(float(fallback_width), 1.0)
    edges = np.empty(vals.size + 1, dtype=float)
    edges[1:-1] = 0.5 * (vals[:-1] + vals[1:])
    edges[0] = vals[0] - delta / 2.0
    edges[-1] = vals[-1] + delta / 2.0
    return edges


def _panel_bin_specs(df: pd.DataFrame, plane: int, axis_name: str) -> List[Tuple[float, str]]:
    center_field = "center_deg" if axis_name == "theta" else "center_mm"
    bins: List[Tuple[float, str]] = []
    for col in df.columns:
        match = EFFICIENCY_VECTOR_COL_RE.match(str(col))
        if match is None:
            continue
        if int(match.group("plane")) != plane or str(match.group("axis")) != axis_name:
            continue
        if str(match.group("field")) != "eff":
            continue
        bin_idx = int(match.group("bin"))
        center_col = f"efficiency_vector_p{plane}_{axis_name}_bin_{bin_idx:03d}_{center_field}"
        if center_col not in df.columns:
            continue
        centers = pd.to_numeric(df[center_col], errors="coerce")
        finite_centers = centers[np.isfinite(centers.to_numpy(dtype=float))]
        if finite_centers.empty:
            continue
        bins.append((float(finite_centers.iloc[0]), str(col)))
    bins.sort(key=lambda item: item[0])
    return bins


def station_time_bounds(df: pd.DataFrame) -> Optional[Tuple[pd.Timestamp, pd.Timestamp]]:
    if df.empty or "file_timestamp" not in df.columns:
        return None
    series = pd.to_datetime(df["file_timestamp"], errors="coerce").dropna()
    if series.empty:
        return None
    lower = pd.Timestamp(series.min())
    upper = pd.Timestamp(series.max())
    if lower == upper:
        upper = lower + timedelta(minutes=1)
    return lower, upper


def plot_panel(
    ax: plt.Axes,
    df: pd.DataFrame,
    *,
    plane: int,
    axis_name: str,
    eff_lim: float,
    max_bin_gap_hours: float,
    x_limits: Optional[Tuple[pd.Timestamp, pd.Timestamp]],
) -> Optional[object]:
    ax.set_title(f"Plane {plane} vs {axis_name.upper()}", fontsize=10)
    ax.set_ylabel(AXIS_LABELS[axis_name])
    if x_limits is not None:
        ax.set_xlim(x_limits[0], x_limits[1])
    bins = _panel_bin_specs(df, plane, axis_name)
    if not bins:
        ax.text(0.5, 0.5, "No vector bins", transform=ax.transAxes, ha="center", va="center", fontsize=9, color="dimgray")
        return None

    time_nums = mdates.date2num(pd.to_datetime(df["file_timestamp"]).to_numpy())
    sort_idx = np.argsort(time_nums)
    time_nums = time_nums[sort_idx]
    centers = np.asarray([item[0] for item in bins], dtype=float)
    value_matrix = (
        df[[item[1] for item in bins]]
        .apply(pd.to_numeric, errors="coerce")
        .to_numpy(dtype=float)
        .T[:, sort_idx]
    )
    x_edges, plot_matrix = build_intervalized_matrix(
        times_num=time_nums,
        value_matrix=value_matrix,
        max_bin_gap_hours=max_bin_gap_hours,
        fallback_seconds=60.0,
    )
    y_edges = compute_axis_edges(
        centers,
        fallback_width=1.0 if axis_name == "theta" else 10.0,
    )
    if x_edges.size == 0 or y_edges.size == 0:
        ax.text(0.5, 0.5, "No eligible rows", transform=ax.transAxes, ha="center", va="center", fontsize=9, color="dimgray")
        return None

    masked = np.ma.masked_where(~np.isfinite(plot_matrix), plot_matrix)
    cmap = plt.get_cmap("viridis")
    ax.set_facecolor(cmap(0.0))
    mesh = ax.pcolormesh(
        x_edges,
        y_edges,
        masked,
        cmap=cmap,
        shading="auto",
        vmin=max(float(eff_lim), 0.0),
        vmax=1.0,
    )
    ax.grid(False)
    return mesh


def plot_station_page(
    station: str,
    df: pd.DataFrame,
    *,
    pdf: PdfPages,
    task_id: int,
    eff_lim: float,
    max_bin_gap_hours: float,
    allowed_count: int,
) -> None:
    fig, axes = plt.subplots(
        len(AXIS_ORDER),
        4,
        figsize=(18, 11.5),
        sharex=True,
        constrained_layout=True,
    )
    bounds = station_time_bounds(df)
    fig.suptitle(
        f"{station} Task {task_id} efficiency metadata heatmaps\n"
        f"Stage-0 gated basenames: {allowed_count} | color scale: [{eff_lim:.2f}, 1.00]",
        fontsize=13,
    )
    last_mesh = None
    for row_idx, axis_name in enumerate(AXIS_ORDER):
        for col_idx, plane in enumerate(range(1, 5)):
            mesh = plot_panel(
                axes[row_idx, col_idx],
                df,
                plane=plane,
                axis_name=axis_name,
                eff_lim=eff_lim,
                max_bin_gap_hours=max_bin_gap_hours,
                x_limits=bounds,
            )
            if mesh is not None:
                last_mesh = mesh
            if row_idx == len(AXIS_ORDER) - 1:
                axes[row_idx, col_idx].set_xlabel("Timestamp from basename")
            axes[row_idx, col_idx].xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=8))
            axes[row_idx, col_idx].xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d\n%H:%M"))
    if last_mesh is not None:
        fig.colorbar(last_mesh, ax=axes.ravel().tolist(), shrink=0.96, label="Efficiency")
    pdf_save_rasterized_page(pdf, fig, dpi=150)
    plt.close(fig)


def load_config(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def resolve_output_path(config: dict, output_override: Optional[str]) -> Path:
    raw = output_override if output_override not in (None, "") else config.get("output", DEFAULT_OUTPUT_FILENAME)
    path = Path(str(raw))
    if not path.is_absolute():
        path = (PLOTTER_DIR / path).resolve()
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plot Task 4 efficiency-vs-X/Y/theta metadata as time heatmaps."
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help=f"Path to JSON config (default: {DEFAULT_CONFIG_PATH}).",
    )
    parser.add_argument("--output", default=None, help="Optional output PDF path.")
    return parser


def main() -> int:
    configure_matplotlib_style()
    args = build_parser().parse_args()
    config = load_config(Path(args.config))
    output_path = resolve_output_path(config, args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    stations = resolve_station_selection(config.get("stations", []))
    task_id = int(config.get("task_id", DEFAULT_TASK_ID))
    tail_rows = int(config.get("tail_rows", DEFAULT_TAIL_ROWS) or 0)
    eff_lim = float(config.get("eff_lim", DEFAULT_EFF_LIM))
    max_bin_gap_hours = float(config.get("max_bin_gap_hours", DEFAULT_MAX_BIN_GAP_HOURS))

    if not stations:
        print("[efficiency_metadata_plotter] No stations selected.", file=sys.stderr)
        return 1

    pages_written = 0
    with PdfPages(output_path) as pdf:
        for station in stations:
            allowed_basenames = load_allowed_basenames(station)
            df = load_efficiency_metadata(
                station=station,
                task_id=task_id,
                allowed_basenames=allowed_basenames,
                tail_rows=tail_rows,
            )
            if df.empty:
                continue
            plot_station_page(
                station,
                df,
                pdf=pdf,
                task_id=task_id,
                eff_lim=eff_lim,
                max_bin_gap_hours=max_bin_gap_hours,
                allowed_count=len(allowed_basenames),
            )
            pages_written += 1

    if pages_written == 0:
        print("[efficiency_metadata_plotter] SKIP: no usable efficiency metadata; inspect efficiency_metadata_reason in Task 4 metadata.", file=sys.stderr)
        return 3
    print(f"[efficiency_metadata_plotter] Wrote {pages_written} page(s) to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
