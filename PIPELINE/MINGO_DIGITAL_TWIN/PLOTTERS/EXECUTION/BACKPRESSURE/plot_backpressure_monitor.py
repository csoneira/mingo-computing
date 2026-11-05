#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_DIGITAL_TWIN/PLOTTERS/EXECUTION/BACKPRESSURE/plot_backpressure_monitor.py
Purpose: Track STEP_0 backpressure state against param_mesh growth.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_DIGITAL_TWIN/PLOTTERS/EXECUTION/BACKPRESSURE/plot_backpressure_monitor.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages

THIS_FILE = Path(__file__).resolve()
PLOTTER_DIR = THIS_FILE.parent
DT_ROOT = next(
    (parent for parent in THIS_FILE.parents if parent.name == "MINGO_DIGITAL_TWIN"),
    THIS_FILE.parents[3],
)
REPO_ROOT = DT_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.plot_utils import pdf_save_rasterized_page

DEFAULT_FREQUENCY_CONFIG = DT_ROOT / "CONFIG_FILES" / "sim_main_pipeline_frequency.conf"
DEFAULT_MESH_PATH = DT_ROOT / "SIMULATION_OUTPUTS" / "INTERSTEPS" / "STEP_0_TO_1" / "param_mesh.csv"
DEFAULT_HISTORY_PATH = PLOTTER_DIR / "backpressure_monitor_history.csv"
DEFAULT_OUTPUT_PATH = PLOTTER_DIR / "backpressure_monitor.pdf"

HISTORY_COLUMNS = [
    "timestamp_utc",
    "pending_total",
    "unique_mi_total",
    "duplicate_entries",
    "simulated_root",
    "simulated_files",
    "unprocessed",
    "processing",
    "unique_simulated_root",
    "unique_simulated_files",
    "unique_unprocessed",
    "unique_processing",
    "overlap_sr_sf",
    "overlap_sr_u",
    "overlap_sr_p",
    "overlap_sf_u",
    "overlap_sf_p",
    "overlap_u_p",
    "threshold",
    "backpressure_blocked",
    "mesh_rows",
    "mesh_delta_rows",
    "mesh_new_rows",
    "status",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Append one backpressure sample and regenerate a monitoring plot. "
            "Intended to be run periodically (for example every 10 minutes)."
        )
    )
    parser.add_argument(
        "--frequency-config",
        type=Path,
        default=DEFAULT_FREQUENCY_CONFIG,
        help=f"Path to sim_main_pipeline_frequency.conf (default: {DEFAULT_FREQUENCY_CONFIG})",
    )
    parser.add_argument(
        "--mesh",
        type=Path,
        default=DEFAULT_MESH_PATH,
        help=f"Path to STEP_0 param_mesh.csv (default: {DEFAULT_MESH_PATH})",
    )
    parser.add_argument(
        "--history",
        type=Path,
        default=DEFAULT_HISTORY_PATH,
        help=f"CSV history file to append per invocation (default: {DEFAULT_HISTORY_PATH})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=f"Output monitor plot (default: {DEFAULT_OUTPUT_PATH})",
    )
    parser.add_argument(
        "--no-plot",
        action="store_true",
        help="Append history only; skip figure generation.",
    )
    return parser.parse_args()


def _extract_mi_id(name: str) -> str | None:
    match = re.search(r"(mi\d{13})", name)
    if not match:
        return None
    return match.group(1)


def _mi_id_set(paths) -> set[str]:
    ids: set[str] = set()
    for path in paths:
        if not path.is_file():
            continue
        mi_id = _extract_mi_id(path.name)
        if mi_id:
            ids.add(mi_id)
    return ids


def count_pending_files() -> dict[str, int]:
    simulated_data_dir = DT_ROOT / "SIMULATION_OUTPUTS" / "SIMULATED_DATA"
    simulated_data_files_dir = simulated_data_dir / "FILES"
    stations_step1_dir = REPO_ROOT / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS" / "MINGO00" / "STAGE_1" / "EVENT_DATA" / "STEP_1"

    sim_root_files = (
        [path for path in simulated_data_dir.glob("mi*.dat") if path.is_file()]
        if simulated_data_dir.exists()
        else []
    )
    sim_files_files = (
        [path for path in simulated_data_files_dir.glob("mi*.dat") if path.is_file()]
        if simulated_data_files_dir.exists()
        else []
    )
    unprocessed_files = (
        [
            path
            for path in stations_step1_dir.glob("TASK_*/INPUT_FILES/UNPROCESSED_DIRECTORY/*")
            if path.is_file()
        ]
        if stations_step1_dir.exists()
        else []
    )
    processing_files = (
        [
            path
            for path in stations_step1_dir.glob("TASK_*/INPUT_FILES/PROCESSING_DIRECTORY/*")
            if path.is_file()
        ]
        if stations_step1_dir.exists()
        else []
    )

    n_sim_root = len(sim_root_files)
    n_sim_files = len(sim_files_files)
    n_unprocessed = len(unprocessed_files)
    n_processing = len(processing_files)

    total = n_sim_root + n_sim_files + n_unprocessed + n_processing
    sets = {
        "sim_root": _mi_id_set(sim_root_files),
        "sim_files": _mi_id_set(sim_files_files),
        "unprocessed": _mi_id_set(unprocessed_files),
        "processing": _mi_id_set(processing_files),
    }
    unique_mi_total = len(set().union(*sets.values()))
    duplicate_entries = max(total - unique_mi_total, 0)

    return {
        "simulated_root": int(n_sim_root),
        "simulated_files": int(n_sim_files),
        "unprocessed": int(n_unprocessed),
        "processing": int(n_processing),
        "pending_total": int(total),
        "unique_mi_total": int(unique_mi_total),
        "duplicate_entries": int(duplicate_entries),
        "unique_simulated_root": int(len(sets["sim_root"])),
        "unique_simulated_files": int(len(sets["sim_files"])),
        "unique_unprocessed": int(len(sets["unprocessed"])),
        "unique_processing": int(len(sets["processing"])),
        "overlap_sr_sf": int(len(sets["sim_root"] & sets["sim_files"])),
        "overlap_sr_u": int(len(sets["sim_root"] & sets["unprocessed"])),
        "overlap_sr_p": int(len(sets["sim_root"] & sets["processing"])),
        "overlap_sf_u": int(len(sets["sim_files"] & sets["unprocessed"])),
        "overlap_sf_p": int(len(sets["sim_files"] & sets["processing"])),
        "overlap_u_p": int(len(sets["unprocessed"] & sets["processing"])),
    }


def read_backpressure_threshold(config_path: Path) -> int:
    if not config_path.exists():
        return 0
    pattern = re.compile(
        r'^\s*SIM_MAX_UNPROCESSED_FILES\s*=\s*"?([0-9]+)"?\s*(?:#.*)?$'
    )
    for line in config_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = pattern.match(line)
        if match:
            return int(match.group(1))
    return 0


def count_mesh_rows(mesh_path: Path) -> int:
    if not mesh_path.exists():
        return 0
    with mesh_path.open("r", encoding="utf-8", newline="") as handle:
        row_count = sum(1 for _ in handle)
    return max(int(row_count) - 1, 0)


def _read_history_rows_tolerant(history_path: Path) -> list[dict[str, str]]:
    if not history_path.exists() or history_path.stat().st_size == 0:
        return []

    rows: list[dict[str, str]] = []
    with history_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = [value.strip() for value in next(reader)]
        except StopIteration:
            return []

        for raw_row in reader:
            if not raw_row:
                continue
            # If the row already has the full current schema width, trust
            # positional order with HISTORY_COLUMNS.
            if len(raw_row) >= len(HISTORY_COLUMNS):
                rows.append(
                    {
                        column: raw_row[idx] if idx < len(raw_row) else ""
                        for idx, column in enumerate(HISTORY_COLUMNS)
                    }
                )
                continue

            row_map: dict[str, str] = {}
            for idx, column in enumerate(header):
                if not column:
                    continue
                row_map[column] = raw_row[idx] if idx < len(raw_row) else ""
            rows.append(row_map)
    return rows


def _history_header_matches(history_path: Path) -> bool:
    if not history_path.exists() or history_path.stat().st_size == 0:
        return False
    with history_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = [value.strip() for value in next(reader)]
        except StopIteration:
            return False
    return header == HISTORY_COLUMNS


def _rewrite_history_with_current_schema(history_path: Path) -> None:
    rows = _read_history_rows_tolerant(history_path)
    with history_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=HISTORY_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in HISTORY_COLUMNS})


def load_last_mesh_rows(history_path: Path) -> int | None:
    if not history_path.exists():
        return None
    history_df = load_history(history_path)
    if "mesh_rows" not in history_df.columns or history_df.empty:
        return None
    numeric = pd.to_numeric(history_df["mesh_rows"], errors="coerce").dropna()
    if numeric.empty:
        return None
    return int(numeric.iloc[-1])


def evaluate_status(threshold: int, pending_total: int, mesh_new_rows: int) -> str:
    if threshold <= 0:
        return "gate_disabled"
    if pending_total >= threshold and mesh_new_rows == 0:
        return "blocked_expected"
    if pending_total >= threshold and mesh_new_rows > 0:
        return "unexpected_growth_while_blocked"
    if pending_total < threshold and mesh_new_rows > 0:
        return "growth_expected"
    return "no_growth_while_unblocked"


def append_history(history_path: Path, row: dict[str, object]) -> None:
    history_path.parent.mkdir(parents=True, exist_ok=True)
    if history_path.exists() and history_path.stat().st_size > 0 and not _history_header_matches(history_path):
        _rewrite_history_with_current_schema(history_path)
    write_header = (not history_path.exists()) or history_path.stat().st_size == 0
    with history_path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=HISTORY_COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerow({column: row.get(column, "") for column in HISTORY_COLUMNS})


def load_history(history_path: Path) -> pd.DataFrame:
    if not history_path.exists():
        return pd.DataFrame(columns=HISTORY_COLUMNS)

    rows = _read_history_rows_tolerant(history_path)
    if not rows:
        return pd.DataFrame(columns=HISTORY_COLUMNS)
    df = pd.DataFrame(rows)
    for column in HISTORY_COLUMNS:
        if column not in df.columns:
            df[column] = ""
    df = df[HISTORY_COLUMNS]

    for column in (
        "pending_total",
        "unique_mi_total",
        "duplicate_entries",
        "simulated_root",
        "simulated_files",
        "unprocessed",
        "processing",
        "unique_simulated_root",
        "unique_simulated_files",
        "unique_unprocessed",
        "unique_processing",
        "overlap_sr_sf",
        "overlap_sr_u",
        "overlap_sr_p",
        "overlap_sf_u",
        "overlap_sf_p",
        "overlap_u_p",
        "threshold",
        "backpressure_blocked",
        "mesh_rows",
        "mesh_delta_rows",
        "mesh_new_rows",
    ):
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    df["timestamp_utc"] = pd.to_datetime(df.get("timestamp_utc"), utc=True, errors="coerce")
    df = df[df["timestamp_utc"].notna()].sort_values("timestamp_utc").reset_index(drop=True)
    return df


def _bar_width_days(times: pd.Series) -> float:
    if times.size <= 1:
        return 0.006
    diffs_sec = times.diff().dropna().dt.total_seconds()
    if diffs_sec.empty:
        return 0.006
    median_days = float(diffs_sec.median()) / 86400.0
    return max(0.002, min(0.15, median_days * 0.8))


# ── Colour palette (shared between full-history and 2-h panels) ──────────────
_C = {
    "pending_total":   "#1f77b4",
    "unique_mi_total": "#333333",
    "duplicate":       "#d62728",
    "sim_root":        "#2ca02c",
    "sim_files":       "#17becf",
    "unprocessed":     "#ff7f0e",
    "processing":      "#9467bd",
    "threshold":       "#c0392b",
    "mesh_new":        "#e67e22",
    "mesh_total":      "#2980b9",
}


def _apply_x_formatter(ax: plt.Axes, is_zoom: bool) -> None:
    if is_zoom:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=mdates.UTC))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=6))
    else:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d\n%H:%M", tz=mdates.UTC))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=8))
    for tick in ax.get_xticklabels():
        tick.set_fontsize(7.5)


def _plot_pending_panel(
    ax: plt.Axes,
    df: pd.DataFrame,
    ts_plot: pd.Series,
    show_legend: bool = True,
    is_zoom: bool = False,
) -> None:
    """Plot the pending-files panel onto *ax*."""
    # Primary summary lines (bold)
    ax.plot(ts_plot, df["pending_total"], color=_C["pending_total"],
            lw=2.2, zorder=4, label="pending total")
    ax.plot(ts_plot, df["unique_mi_total"].fillna(0), color=_C["unique_mi_total"],
            lw=1.6, ls="--", zorder=4, label="unique total")

    # Component breakdown (thinner, semi-transparent)
    ax.plot(ts_plot, df["simulated_root"],    color=_C["sim_root"],   lw=1.0, alpha=0.75, label="sim_root")
    ax.plot(ts_plot, df["simulated_files"],   color=_C["sim_files"],  lw=1.0, alpha=0.75, label="sim_files")
    ax.plot(ts_plot, df["unprocessed"],       color=_C["unprocessed"], lw=1.0, alpha=0.75, label="unprocessed")
    ax.plot(ts_plot, df["processing"],        color=_C["processing"], lw=1.0, alpha=0.75, label="processing")

    # Duplicates (secondary diagnostic, dashed)
    dupes = df["duplicate_entries"].fillna(0)
    if dupes.gt(0).any():
        ax.plot(ts_plot, dupes, color=_C["duplicate"], lw=1.0, ls=":", alpha=0.85, label="duplicates")

    # Backpressure threshold
    thresholds = df["threshold"].fillna(0)
    if thresholds.gt(0).any():
        ax.plot(ts_plot, thresholds, color=_C["threshold"],
                lw=1.8, ls=(0, (5, 3)), zorder=3, label="threshold")

    # Blocked sample markers
    blocked_mask = df["backpressure_blocked"].fillna(0).astype(int) == 1
    if blocked_mask.any():
        ax.scatter(ts_plot[blocked_mask], df.loc[blocked_mask, "pending_total"],
                   color="red", marker="x", s=30, lw=1.5, zorder=5, label="blocked")

    ax.set_ylabel("Files", fontsize=9)
    ax.tick_params(axis="y", labelsize=8)
    ax.grid(True, ls=":", lw=0.5, alpha=0.5)

    if show_legend:
        leg = ax.legend(
            loc="upper left",
            ncol=2 if not is_zoom else 1,
            fontsize=7.5,
            framealpha=0.88,
            handlelength=1.8,
            labelspacing=0.3,
            borderpad=0.5,
        )
        leg.get_frame().set_linewidth(0.5)


def _plot_mesh_panel(
    ax: plt.Axes,
    df: pd.DataFrame,
    ts_plot: pd.Series,
    bar_width: float,
    show_ylabel_right: bool = True,
) -> plt.Axes:
    """Plot the mesh-growth panel; returns the twinx axes."""
    ax.bar(ts_plot, df["mesh_new_rows"].fillna(0), width=bar_width,
           color=_C["mesh_new"], alpha=0.72, label="new rows/run")
    ax.axhline(0.0, color="black", lw=0.6, alpha=0.5)
    ax.set_ylabel("New Rows / Run", fontsize=9)
    ax.tick_params(axis="y", labelsize=8)
    ax.grid(True, ls=":", lw=0.5, alpha=0.5)
    ax.yaxis.get_major_locator().set_params(integer=True)

    ax_r = ax.twinx()
    ax_r.plot(ts_plot, df["mesh_rows"].fillna(0), color=_C["mesh_total"],
              lw=1.6, marker="o", ms=2.5, label="total rows")
    if show_ylabel_right:
        ax_r.set_ylabel("Total Mesh Rows", fontsize=9)
    ax_r.tick_params(axis="y", labelsize=8)

    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax_r.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=7.5,
              framealpha=0.88, handlelength=1.8, labelspacing=0.3, borderpad=0.5)
    return ax_r


def build_plot(history_df: pd.DataFrame, output_path: Path) -> None:
    if history_df.empty:
        return

    plt.style.use("seaborn-v0_8-whitegrid")

    # ── Slice out the last-2-h window ────────────────────────────────────────
    now_utc = history_df["timestamp_utc"].max()
    cutoff_2h = now_utc - pd.Timedelta(hours=2)
    df_2h = history_df[history_df["timestamp_utc"] >= cutoff_2h].copy()
    has_zoom_data = not df_2h.empty

    # ── Figure / gridspec ────────────────────────────────────────────────────
    fig = plt.figure(figsize=(19.0, 8.5))
    gs = fig.add_gridspec(
        2, 2,
        width_ratios=[2.6, 1.0],
        height_ratios=[2.2, 1.2],
        hspace=0.38,
        wspace=0.10,
        left=0.06, right=0.97, top=0.91, bottom=0.09,
    )
    ax_top_full = fig.add_subplot(gs[0, 0])
    ax_bot_full = fig.add_subplot(gs[1, 0], sharex=ax_top_full)
    ax_top_2h   = fig.add_subplot(gs[0, 1])
    ax_bot_2h   = fig.add_subplot(gs[1, 1])

    # ── Full-history panel (left column) ─────────────────────────────────────
    ts_full = history_df["timestamp_utc"].dt.tz_convert(None)
    _plot_pending_panel(ax_top_full, history_df, ts_full, show_legend=True, is_zoom=False)
    ax_top_full.set_title("Pending Files — full history", fontsize=10, fontweight="bold")

    bar_w_full = _bar_width_days(history_df["timestamp_utc"])
    ax_bot_full_r = _plot_mesh_panel(ax_bot_full, history_df, ts_full, bar_w_full, show_ylabel_right=True)
    ax_bot_full.set_title("param_mesh Growth — full history", fontsize=10, fontweight="bold")
    ax_bot_full.set_xlabel("UTC Date / Time", fontsize=9)
    _apply_x_formatter(ax_bot_full, is_zoom=False)
    plt.setp(ax_top_full.get_xticklabels(), visible=False)

    # ── Last-2-h zoom panel (right column) ───────────────────────────────────
    if has_zoom_data:
        ts_2h = df_2h["timestamp_utc"].dt.tz_convert(None)
        _plot_pending_panel(ax_top_2h, df_2h, ts_2h, show_legend=True, is_zoom=True)

        bar_w_2h = _bar_width_days(df_2h["timestamp_utc"])
        ax_bot_2h_r = _plot_mesh_panel(ax_bot_2h, df_2h, ts_2h, bar_w_2h, show_ylabel_right=True)

        ax_bot_2h.set_xlabel("UTC Time (last 2 h)", fontsize=9)
        _apply_x_formatter(ax_bot_2h, is_zoom=True)
        plt.setp(ax_top_2h.get_xticklabels(), visible=False)
    else:
        for ax in (ax_top_2h, ax_bot_2h):
            ax.text(0.5, 0.5, "No data\nin last 2 h",
                    ha="center", va="center", transform=ax.transAxes,
                    fontsize=10, color="gray")
            ax.set_axis_off()

    ax_top_2h.set_title("Last 2 h", fontsize=10, fontweight="bold")
    ax_bot_2h.set_title("Last 2 h", fontsize=10, fontweight="bold")

    # ── Suptitle with last-sample timestamp ──────────────────────────────────
    last_ts = now_utc.strftime("%Y-%m-%d %H:%M UTC") if hasattr(now_utc, "strftime") else str(now_utc)
    fig.suptitle(f"STEP_0 Backpressure Monitor   [last sample: {last_ts}]",
                 fontsize=13, fontweight="bold")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.suffix.lower() == ".pdf":
        with PdfPages(output_path) as pdf:
            pdf_save_rasterized_page(pdf, fig, dpi=160)
    else:
        fig.savefig(output_path, dpi=160)
    plt.close(fig)


def main() -> None:
    args = parse_args()

    threshold = read_backpressure_threshold(args.frequency_config)
    pending = count_pending_files()
    mesh_rows = count_mesh_rows(args.mesh)
    previous_mesh_rows = load_last_mesh_rows(args.history)

    if previous_mesh_rows is None:
        mesh_delta_rows = 0
    else:
        mesh_delta_rows = int(mesh_rows - previous_mesh_rows)
    mesh_new_rows = int(max(mesh_delta_rows, 0))

    blocked = int(threshold > 0 and pending["pending_total"] >= threshold)
    status = evaluate_status(threshold, pending["pending_total"], mesh_new_rows)

    row = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "pending_total": int(pending["pending_total"]),
        "unique_mi_total": int(pending["unique_mi_total"]),
        "duplicate_entries": int(pending["duplicate_entries"]),
        "simulated_root": int(pending["simulated_root"]),
        "simulated_files": int(pending["simulated_files"]),
        "unprocessed": int(pending["unprocessed"]),
        "processing": int(pending["processing"]),
        "unique_simulated_root": int(pending["unique_simulated_root"]),
        "unique_simulated_files": int(pending["unique_simulated_files"]),
        "unique_unprocessed": int(pending["unique_unprocessed"]),
        "unique_processing": int(pending["unique_processing"]),
        "overlap_sr_sf": int(pending["overlap_sr_sf"]),
        "overlap_sr_u": int(pending["overlap_sr_u"]),
        "overlap_sr_p": int(pending["overlap_sr_p"]),
        "overlap_sf_u": int(pending["overlap_sf_u"]),
        "overlap_sf_p": int(pending["overlap_sf_p"]),
        "overlap_u_p": int(pending["overlap_u_p"]),
        "threshold": int(threshold),
        "backpressure_blocked": int(blocked),
        "mesh_rows": int(mesh_rows),
        "mesh_delta_rows": int(mesh_delta_rows),
        "mesh_new_rows": int(mesh_new_rows),
        "status": status,
    }
    append_history(args.history, row)

    if not args.no_plot:
        history_df = load_history(args.history)
        build_plot(history_df, args.output)

    print(
        "backpressure_monitor "
        f"pending_total={row['pending_total']} "
        f"unique_mi_total={row['unique_mi_total']} "
        f"duplicate_entries={row['duplicate_entries']} "
        f"threshold={row['threshold']} "
        f"blocked={row['backpressure_blocked']} "
        f"mesh_rows={row['mesh_rows']} "
        f"mesh_new_rows={row['mesh_new_rows']} "
        f"status={row['status']} "
        f"history={args.history} "
        f"plot={args.output if not args.no_plot else 'disabled'}"
    )


if __name__ == "__main__":
    main()
