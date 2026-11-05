#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/NOTIFICATIONS/STATUS_GUI/simulation_status_timeline_gui.py
Purpose: Real-time simulation execution-time timeline viewer (Tkinter, X11-friendly).
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-03
Runtime: python3
Usage: python3 CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/NOTIFICATIONS/STATUS_GUI/simulation_status_timeline_gui.py [options]
Inputs: PIPELINE/MINGO_DIGITAL_TWIN/PLOTTERS/EXECUTION/SIMULATION_TIME/simulation_execution_times.csv
Outputs: GUI or terminal snapshot.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

CSV_DEFAULT_REL = (
    "PIPELINE/MINGO_DIGITAL_TWIN/PLOTTERS/EXECUTION/SIMULATION_TIME/simulation_execution_times.csv"
)

DATE_FORMATS = (
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d_%H.%M.%S",
)


@dataclass(frozen=True)
class SimExecRecord:
    duration: float      # wall-clock duration of the step run (seconds, column 1)
    step: int            # simulation step number (column 2)
    timestamp: datetime  # time the execution was recorded (column 3)


def _parse_datetime(value: str) -> Optional[datetime]:
    text = value.strip().rstrip("Z")
    if not text:
        return None
    for fmt in DATE_FORMATS:
        candidate = fmt.rstrip("Z") if fmt.endswith("Z") else fmt
        try:
            return datetime.strptime(text, candidate)
        except ValueError:
            continue
    return None


def load_sim_exec_records(
    csv_path: Path,
    *,
    now: Optional[datetime] = None,
    lookback: timedelta,
    step_filter: Optional[set[int]] = None,
) -> list[SimExecRecord]:
    """Read the headerless CSV and return records within the lookback window."""
    # CSV timestamps are recorded in UTC (trailing "Z").
    # Keep all comparisons in naive-UTC to avoid local-time offset filtering bugs.
    current_time = now or datetime.utcnow()
    min_time = current_time - lookback
    records: list[SimExecRecord] = []

    if not csv_path.exists():
        return records

    try:
        with csv_path.open(newline="") as fh:
            reader = csv.reader(fh)
            for row in reader:
                if len(row) < 3:
                    continue
                try:
                    duration = float(row[0])
                    step = int(row[1])
                except (ValueError, IndexError):
                    continue
                ts = _parse_datetime(row[2])
                if ts is None or ts < min_time:
                    continue
                if step_filter is not None and step not in step_filter:
                    continue
                records.append(SimExecRecord(duration=duration, step=step, timestamp=ts))
    except (OSError, csv.Error):
        pass

    records.sort(key=lambda r: r.timestamp)
    return records


def _turbo_color(value: float) -> str:
    """Map a normalised value in [0, 1] to a hex colour via the turbo colormap."""
    try:
        from matplotlib import colormaps
        rgba = colormaps["turbo"](max(0.0, min(1.0, value)))
        r, g, b = int(rgba[0] * 255), int(rgba[1] * 255), int(rgba[2] * 255)
        return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:
        # Graceful fallback: blue → red gradient
        r = int(255 * value)
        b = int(255 * (1.0 - value))
        return f"#{r:02x}00{b:02x}"


def _duration_to_color(duration: float, vmin: float, vmax: float) -> str:
    span = max(vmax - vmin, 1e-9)
    return _turbo_color(max(0.0, min(1.0, (duration - vmin) / span)))


def _parse_step_filter(text: str) -> tuple[Optional[set[int]], Optional[str]]:
    cleaned = text.strip().lower()
    if cleaned in {"", "all", "*"}:
        return None, None
    values: set[int] = set()
    for token in cleaned.replace(";", ",").split(","):
        token = token.strip()
        if not token:
            continue
        if not token.isdigit():
            return None, f"Invalid step value: {token!r}"
        values.add(int(token))
    if not values:
        return None, "No valid steps provided."
    return values, None


class SimExecTimelineApp:
    def __init__(self, root, tk_module, ttk_module, args: argparse.Namespace) -> None:
        self.root = root
        self.tk = tk_module
        self.ttk = ttk_module
        self.csv_path = args.csv_path.resolve()
        self.max_rows = args.max_rows
        self.records: list[SimExecRecord] = []
        self.after_id: Optional[str] = None

        self.lookback_var = self.tk.StringVar(value=str(args.lookback_hours))
        self.refresh_var = self.tk.StringVar(value=str(args.refresh_seconds))
        self.step_var = self.tk.StringVar(value=args.steps)
        self.auto_refresh_var = self.tk.BooleanVar(value=True)
        self.status_var = self.tk.StringVar(value="Waiting for first refresh...")

        self._build_ui()
        self._refresh_now()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.root.title("Simulation Execution Time Timeline")
        self.root.geometry("1280x780")

        controls = self.ttk.Frame(self.root, padding=8)
        controls.pack(fill="x")

        self.ttk.Label(controls, text="Lookback (hours)").pack(side="left")
        self.ttk.Entry(controls, width=8, textvariable=self.lookback_var).pack(
            side="left", padx=(4, 12)
        )

        self.ttk.Label(controls, text="Refresh (s)").pack(side="left")
        self.ttk.Entry(controls, width=6, textvariable=self.refresh_var).pack(
            side="left", padx=(4, 12)
        )

        self.ttk.Label(controls, text="Steps").pack(side="left")
        self.ttk.Entry(controls, width=16, textvariable=self.step_var).pack(
            side="left", padx=(4, 12)
        )

        self.ttk.Checkbutton(
            controls, text="Auto Refresh", variable=self.auto_refresh_var
        ).pack(side="left", padx=(0, 12))

        self.ttk.Button(controls, text="Refresh Now", command=self._refresh_now).pack(
            side="left"
        )

        self.canvas = self.tk.Canvas(self.root, bg="white", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.canvas.bind("<Configure>", lambda _event: self._draw_timeline())

        table_frame = self.ttk.Frame(self.root, padding=(8, 0, 8, 8))
        table_frame.pack(fill="both", expand=False)

        columns = ("timestamp", "step", "duration")
        self.table = self.ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            height=9,
        )
        self.table.heading("timestamp", text="Execution Timestamp")
        self.table.heading("step", text="Step")
        self.table.heading("duration", text="Duration (s)")
        self.table.column("timestamp", width=180, anchor="w")
        self.table.column("step", width=80, anchor="center")
        self.table.column("duration", width=120, anchor="center")

        scrollbar = self.ttk.Scrollbar(
            table_frame, orient="vertical", command=self.table.yview
        )
        self.table.configure(yscrollcommand=scrollbar.set)
        self.table.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="left", fill="y")

        status_bar = self.ttk.Label(
            self.root, textvariable=self.status_var, anchor="w", padding=(8, 0, 8, 8)
        )
        status_bar.pack(fill="x")

    # ------------------------------------------------------------------
    # Refresh logic
    # ------------------------------------------------------------------

    def _read_config(self) -> tuple[Optional[dict], Optional[str]]:
        try:
            lookback_hours = float(self.lookback_var.get())
            refresh_seconds = int(self.refresh_var.get())
        except ValueError:
            return None, "Lookback and refresh must be numeric."
        if lookback_hours <= 0:
            return None, "Lookback must be > 0 hours."
        if refresh_seconds <= 0:
            return None, "Refresh must be > 0 seconds."

        steps, step_error = _parse_step_filter(self.step_var.get())
        if step_error:
            return None, step_error

        return {
            "lookback_hours": lookback_hours,
            "refresh_seconds": refresh_seconds,
            "steps": steps,
        }, None

    def _refresh_now(self) -> None:
        if self.after_id is not None:
            self.root.after_cancel(self.after_id)
            self.after_id = None

        config, error = self._read_config()
        if error is not None:
            self.status_var.set(f"Configuration error: {error}")
            self._schedule_next(5)
            return

        assert config is not None
        now_utc = datetime.utcnow()
        now_local = datetime.now()
        self.records = load_sim_exec_records(
            self.csv_path,
            now=now_utc,
            lookback=timedelta(hours=float(config["lookback_hours"])),
            step_filter=config["steps"],
        )
        self._draw_timeline()
        self._fill_table()

        latest = (
            self.records[-1].timestamp.strftime("%Y-%m-%d %H:%M:%S")
            if self.records
            else "-"
        )
        self.status_var.set(
            f"Records: {len(self.records)} | Latest (UTC): {latest} | "
            f"Last refresh (local): {now_local.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        self._schedule_next(int(config["refresh_seconds"]))

    def _schedule_next(self, refresh_seconds: int) -> None:
        if not self.auto_refresh_var.get():
            return
        self.after_id = self.root.after(refresh_seconds * 1000, self._refresh_now)

    # ------------------------------------------------------------------
    # Canvas drawing
    # ------------------------------------------------------------------

    def _draw_timeline(self) -> None:
        self.canvas.delete("all")
        width = max(self.canvas.winfo_width(), 600)
        height = max(self.canvas.winfo_height(), 240)

        config, error = self._read_config()
        if error is not None or config is None:
            self.canvas.create_text(
                width // 2, height // 2,
                text=f"Configuration error: {error}",
                fill="red", font=("TkDefaultFont", 12, "bold"),
            )
            return

        if not self.records:
            self.canvas.create_text(
                width // 2, height // 2,
                text="No records in selected lookback window.",
                fill="#444444", font=("TkDefaultFont", 12, "bold"),
            )
            return

        now = datetime.utcnow()
        lookback = timedelta(hours=float(config["lookback_hours"]))
        start_time = now - lookback
        end_time = now

        # Layout constants
        colorbar_w = 18
        colorbar_right_pad = 62
        left = 80
        right = width - colorbar_right_pad - colorbar_w - 12
        top = 30
        bottom = height - 36

        # Colorbar bounding box (right side of canvas)
        cb_x0 = width - colorbar_right_pad - colorbar_w
        cb_x1 = width - colorbar_right_pad
        cb_y0 = top
        cb_y1 = bottom

        # Step lanes
        steps_present = sorted({r.step for r in self.records})
        lane_count = len(steps_present)
        step_lane_index = {s: i for i, s in enumerate(steps_present)}
        lane_height = max((bottom - top) / max(lane_count, 1), 24)

        def x_for_time(moment: datetime) -> float:
            span = max((end_time - start_time).total_seconds(), 1.0)
            elapsed = (moment - start_time).total_seconds()
            return left + (right - left) * (elapsed / span)

        # Vertical time-grid lines and tick labels
        for tick in range(6):
            fraction = tick / 5
            tick_x = left + (right - left) * fraction
            tick_time = start_time + (end_time - start_time) * fraction
            self.canvas.create_line(tick_x, top - 6, tick_x, bottom + 4, fill="#e5e5e5")
            self.canvas.create_text(
                tick_x, bottom + 16,
                text=tick_time.strftime("%H:%M:%S"),
                fill="#555555", font=("TkDefaultFont", 8),
            )

        # Horizontal lane guide lines and step labels
        for step, idx in step_lane_index.items():
            y = top + idx * lane_height + lane_height / 2
            self.canvas.create_line(left, y, right, y, fill="#f0f0f0")
            self.canvas.create_text(
                left - 8, y,
                text=f"STEP {step}",
                anchor="e", font=("TkDefaultFont", 9, "bold"),
            )

        # Colormap normalisation range
        durations = [r.duration for r in self.records]
        vmin = min(durations)
        vmax = max(durations)

        # Data points: X = timestamp, lane = step, colour = duration
        for record in self.records:
            idx = step_lane_index[record.step]
            y = top + idx * lane_height + lane_height / 2
            x = x_for_time(record.timestamp)
            color = _duration_to_color(record.duration, vmin, vmax)
            r = 4
            self.canvas.create_oval(
                x - r, y - r, x + r, y + r,
                fill=color, outline="#333333",
            )

        # Colourbar (vertical gradient, high value at top)
        cb_height = max(int(cb_y1 - cb_y0), 1)
        for i in range(cb_height):
            norm = 1.0 - i / cb_height
            seg_color = _turbo_color(norm)
            self.canvas.create_line(cb_x0, cb_y0 + i, cb_x1, cb_y0 + i, fill=seg_color)
        self.canvas.create_rectangle(cb_x0, cb_y0, cb_x1, cb_y1, outline="#555555")

        # Colourbar tick labels (top, mid, bottom)
        for norm_pos, label_val in (
            (0.0, vmax),
            (0.5, (vmin + vmax) / 2),
            (1.0, vmin),
        ):
            label_y = cb_y0 + norm_pos * (cb_y1 - cb_y0)
            self.canvas.create_text(
                cb_x1 + 4, label_y,
                text=f"{label_val:.1f}s", anchor="w", font=("TkDefaultFont", 8),
            )
        self.canvas.create_text(
            (cb_x0 + cb_x1) / 2, cb_y0 - 10,
            text="dur.", anchor="center", font=("TkDefaultFont", 8),
        )

    # ------------------------------------------------------------------
    # Table
    # ------------------------------------------------------------------

    def _fill_table(self) -> None:
        for item in self.table.get_children():
            self.table.delete(item)
        ordered = sorted(self.records, key=lambda r: r.timestamp, reverse=True)
        for record in ordered[: self.max_rows]:
            self.table.insert(
                "", "end",
                values=(
                    record.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                    f"STEP_{record.step}",
                    f"{record.duration:.3f}",
                ),
            )


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------

def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Real-time simulation execution-time timeline GUI."
    )
    repo_root_default = Path(__file__).resolve().parents[4]
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=repo_root_default,
        help="Repository root (default: auto-detected).",
    )
    parser.add_argument(
        "--csv-path",
        type=Path,
        default=None,
        help=(
            "Path to simulation_execution_times.csv. "
            "Defaults to <repo-root>/" + CSV_DEFAULT_REL
        ),
    )
    parser.add_argument(
        "--lookback-hours",
        type=float,
        default=0.2,
        help="Initial lookback window in hours.",
    )
    parser.add_argument(
        "--refresh-seconds",
        type=int,
        default=30,
        help="Auto-refresh interval in seconds.",
    )
    parser.add_argument(
        "--steps",
        default="all",
        help='Comma-separated step filter (e.g. "1,2,3") or "all".',
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=500,
        help="Maximum rows shown in the table.",
    )
    parser.add_argument(
        "--snapshot",
        action="store_true",
        help="Print a terminal snapshot and exit (no GUI).",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv or sys.argv[1:])

    if args.csv_path is None:
        args.csv_path = args.repo_root.resolve() / CSV_DEFAULT_REL

    if args.snapshot:
        steps, step_error = _parse_step_filter(args.steps)
        if step_error:
            print(step_error, file=sys.stderr)
            return 1
        records = load_sim_exec_records(
            args.csv_path.resolve(),
            now=datetime.utcnow(),
            lookback=timedelta(hours=args.lookback_hours),
            step_filter=steps,
        )
        print(f"records={len(records)}")
        for rec in records[-20:]:
            print(
                f"{rec.timestamp:%Y-%m-%d %H:%M:%S}  STEP_{rec.step:2d}  {rec.duration:.3f}s"
            )
        return 0

    if not os.environ.get("DISPLAY"):
        print(
            "DISPLAY is not set. For remote GUI usage, connect with X11 forwarding "
            "(for example: ssh -X ...).",
            file=sys.stderr,
        )
        return 1

    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception as exc:
        print(f"Tkinter is required for this GUI: {exc}", file=sys.stderr)
        return 1

    root = tk.Tk()
    app = SimExecTimelineApp(root, tk, ttk, args)
    del app
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
