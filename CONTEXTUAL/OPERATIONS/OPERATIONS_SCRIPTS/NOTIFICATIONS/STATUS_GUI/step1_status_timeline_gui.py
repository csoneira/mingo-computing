#!/usr/bin/env python3

"""Real-time STEP_1 status timeline viewer (Tkinter, X11-friendly)."""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

_REPO_IMPORT_ROOT = Path(__file__).resolve().parents[5]
if str(_REPO_IMPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_IMPORT_ROOT))
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.path_config import get_repo_root

from typing import Iterable, Optional


STATUS_FILE_GLOB = (
    "PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO0*/STAGE_1/EVENT_DATA/STEP_1/TASK_*/METADATA/"
    "task_*_metadata_status.csv"
)
DATE_FORMATS = (
    "%Y-%m-%d_%H.%M.%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
)
STATION_RE = re.compile(r"^MINGO0(\d)$")
TASK_RE = re.compile(r"^TASK_(\d+)$")
GUIDE_RELATIVE_PATH = Path("PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_1/EVENT_DATA/guide_raw_to_corrected.sh")
DEFAULT_TASK_LABELS = {
    0: "acq_to_raw",
    1: "raw_to_clean",
    2: "clean_to_cal",
    3: "cal_to_list",
    4: "list_to_fit",
    5: "fit_to_corr",
}


@dataclass(frozen=True)
class StatusEvent:
    station: int
    task: int
    filename_base: str
    execution_time: datetime
    completion: float
    csv_path: Path
    csv_mtime: datetime


def _parse_datetime(value: str) -> Optional[datetime]:
    text = value.strip()
    if not text:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _parse_completion(value: object) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = 0.0
    if numeric == -1.0:
        return -1.0
    return max(0.0, min(1.0, numeric))


def _extract_station_task(path: Path) -> tuple[Optional[int], Optional[int]]:
    station: Optional[int] = None
    task: Optional[int] = None
    for part in path.parts:
        station_match = STATION_RE.match(part)
        if station_match:
            station = int(station_match.group(1))
            continue
        task_match = TASK_RE.match(part)
        if task_match:
            task = int(task_match.group(1))
    return station, task


def _iter_status_files(repo_root: Path) -> Iterable[Path]:
    yield from sorted(repo_root.glob(STATUS_FILE_GLOB))


def _load_task_labels(repo_root: Path) -> dict[int, str]:
    labels = dict(DEFAULT_TASK_LABELS)
    guide_path = repo_root / GUIDE_RELATIVE_PATH
    try:
        text = guide_path.read_text(encoding="utf-8")
    except OSError:
        return labels

    match = re.search(r"TASK_LABELS=\(\s*(.*?)\s*\)", text, flags=re.DOTALL)
    if match is None:
        return labels

    parsed = re.findall(r'"([^"]+)"', match.group(1))
    if not parsed:
        return labels
    for task_id, label in enumerate(parsed):
        labels[task_id] = label
    return labels


def _format_task_label(task_id: int, task_labels: dict[int, str]) -> str:
    label = task_labels.get(task_id)
    if not label:
        return f"TASK_{task_id}"
    return f"TASK_{task_id} {label}"


def load_status_events(
    repo_root: Path,
    *,
    now: Optional[datetime] = None,
    lookback: timedelta,
    station_filter: Optional[set[int]] = None,
    task_filter: Optional[set[int]] = None,
) -> list[StatusEvent]:
    current_time = now or datetime.now()
    min_time = current_time - lookback
    events: list[StatusEvent] = []

    for csv_path in _iter_status_files(repo_root):
        station, task = _extract_station_task(csv_path)
        if station is None or task is None:
            continue
        if station_filter is not None and station not in station_filter:
            continue
        if task_filter is not None and task not in task_filter:
            continue
        try:
            csv_mtime = datetime.fromtimestamp(csv_path.stat().st_mtime)
        except OSError:
            continue

        try:
            with csv_path.open(newline="") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    execution_value = row.get("execution_date") or row.get("timestamp") or ""
                    execution_time = _parse_datetime(execution_value)
                    if execution_time is None or execution_time < min_time:
                        continue
                    filename_base = (
                        row.get("filename_base")
                        or row.get("basename")
                        or "<unknown>"
                    ).strip()
                    completion_value = row.get("completion_fraction", row.get("status", 0))
                    events.append(
                        StatusEvent(
                            station=station,
                            task=task,
                            filename_base=filename_base,
                            execution_time=execution_time,
                            completion=_parse_completion(completion_value),
                            csv_path=csv_path,
                            csv_mtime=csv_mtime,
                        )
                    )
        except (OSError, csv.Error):
            continue

    events.sort(key=lambda item: item.execution_time)
    return events


def _progress_color(progress: float) -> str:
    if progress == -1.0:
        return "#ffffff"
    value = max(0.0, min(1.0, progress))
    if value <= 0.5:
        ratio = value / 0.5 if value > 0 else 0.0
        red = 255
        green = int(255 * ratio)
    else:
        ratio = (value - 0.5) / 0.5
        red = int(255 * (1.0 - ratio))
        green = 255
    return f"#{red:02x}{green:02x}00"


def _completion_label(progress: float) -> str:
    return "no files" if progress == -1.0 else f"{progress:.2f}"


def _parse_id_filter(
    text: str,
    *,
    min_value: int,
    max_value: int,
    label: str,
) -> tuple[Optional[set[int]], Optional[str]]:
    cleaned = text.strip().lower()
    if cleaned in {"", "all", "*"}:
        return None, None

    values: set[int] = set()
    for token in cleaned.replace(";", ",").split(","):
        token = token.strip()
        if not token:
            continue
        if not token.isdigit():
            return None, f"Invalid {label} value: {token}"
        number = int(token)
        if number < min_value or number > max_value:
            return None, f"{label.capitalize()} must be in [{min_value}, {max_value}]"
        values.add(number)

    if not values:
        return None, f"No valid {label} provided."
    return values, None


class StatusTimelineApp:
    def __init__(self, root, tk_module, ttk_module, args: argparse.Namespace) -> None:
        self.root = root
        self.tk = tk_module
        self.ttk = ttk_module
        self.repo_root = args.repo_root.resolve()
        self.max_rows = args.max_rows
        self.events: list[StatusEvent] = []
        self.task_labels = _load_task_labels(self.repo_root)
        self.after_id: Optional[str] = None

        self.lookback_var = self.tk.StringVar(value=str(args.lookback_hours))
        self.refresh_var = self.tk.StringVar(value=str(args.refresh_seconds))
        self.station_var = self.tk.StringVar(value=args.stations)
        self.task_var = self.tk.StringVar(value=args.tasks)
        self.auto_refresh_var = self.tk.BooleanVar(value=True)
        self.status_var = self.tk.StringVar(value="Waiting for first refresh...")

        self._build_ui()
        self._refresh_now()

    def _build_ui(self) -> None:
        self.root.title("STEP_1 Status Timeline")
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

        self.ttk.Label(controls, text="Stations").pack(side="left")
        self.ttk.Entry(controls, width=12, textvariable=self.station_var).pack(
            side="left", padx=(4, 12)
        )

        self.ttk.Label(controls, text="Tasks").pack(side="left")
        self.ttk.Entry(controls, width=12, textvariable=self.task_var).pack(
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

        columns = ("execution", "station", "task", "file", "progress", "source_mtime")
        self.table = self.ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            height=11,
        )
        self.table.heading("execution", text="Execution Time")
        self.table.heading("station", text="Station")
        self.table.heading("task", text="Task")
        self.table.heading("file", text="Filename Base")
        self.table.heading("progress", text="Progress")
        self.table.heading("source_mtime", text="CSV Last Modified")
        self.table.column("execution", width=170, anchor="w")
        self.table.column("station", width=70, anchor="center")
        self.table.column("task", width=70, anchor="center")
        self.table.column("file", width=260, anchor="w")
        self.table.column("progress", width=90, anchor="center")
        self.table.column("source_mtime", width=170, anchor="w")

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

    def _read_filters(self) -> tuple[Optional[dict[str, object]], Optional[str]]:
        try:
            lookback_hours = float(self.lookback_var.get())
            refresh_seconds = int(self.refresh_var.get())
        except ValueError:
            return None, "Lookback and refresh must be numeric."

        if lookback_hours <= 0:
            return None, "Lookback must be > 0 hours."
        if refresh_seconds <= 0:
            return None, "Refresh must be > 0 seconds."

        stations, station_error = _parse_id_filter(
            self.station_var.get(), min_value=0, max_value=4, label="station"
        )
        if station_error:
            return None, station_error

        tasks, task_error = _parse_id_filter(
            self.task_var.get(), min_value=0, max_value=5, label="task"
        )
        if task_error:
            return None, task_error

        return (
            {
                "lookback_hours": lookback_hours,
                "refresh_seconds": refresh_seconds,
                "stations": stations,
                "tasks": tasks,
            },
            None,
        )

    def _refresh_now(self) -> None:
        if self.after_id is not None:
            self.root.after_cancel(self.after_id)
            self.after_id = None

        config, error = self._read_filters()
        if error is not None:
            self.status_var.set(f"Configuration error: {error}")
            self._schedule_next(5)
            return

        assert config is not None
        now = datetime.now()
        lookback = timedelta(hours=float(config["lookback_hours"]))
        self.events = load_status_events(
            self.repo_root,
            now=now,
            lookback=lookback,
            station_filter=config["stations"],
            task_filter=config["tasks"],
        )
        self._draw_timeline()
        self._fill_table()

        no_file = sum(1 for event in self.events if event.completion == -1.0)
        active = sum(1 for event in self.events if 0.0 <= event.completion < 1.0)
        latest = self.events[-1].execution_time.strftime("%Y-%m-%d %H:%M:%S") if self.events else "-"
        self.status_var.set(
            f"Rows: {len(self.events)} | Active (0..1): {active} | No-file: {no_file} | Latest execution: {latest} | "
            f"Last refresh: {now.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        self._schedule_next(int(config["refresh_seconds"]))

    def _schedule_next(self, refresh_seconds: int) -> None:
        if not self.auto_refresh_var.get():
            return
        self.after_id = self.root.after(refresh_seconds * 1000, self._refresh_now)

    def _draw_timeline(self) -> None:
        self.canvas.delete("all")
        width = max(self.canvas.winfo_width(), 600)
        height = max(self.canvas.winfo_height(), 240)

        config, error = self._read_filters()
        if error is not None or config is None:
            self.canvas.create_text(
                width // 2,
                height // 2,
                text=f"Configuration error: {error}",
                fill="red",
                font=("TkDefaultFont", 12, "bold"),
            )
            return

        now = datetime.now()
        lookback = timedelta(hours=float(config["lookback_hours"]))
        start_time = now - lookback
        end_time = now

        if not self.events:
            self.canvas.create_text(
                width // 2,
                height // 2,
                text="No status rows in selected lookback window.",
                fill="#444444",
                font=("TkDefaultFont", 12, "bold"),
            )
            return

        lanes = sorted({(event.station, event.task) for event in self.events})
        lane_count = len(lanes)
        lane_index = {lane: idx for idx, lane in enumerate(lanes)}

        left = 155
        right = width - 20
        top = 24
        bottom = height - 36
        lane_height = max((bottom - top) / max(lane_count, 1), 24)

        def x_for_time(moment: datetime) -> float:
            span = max((end_time - start_time).total_seconds(), 1)
            elapsed = (moment - start_time).total_seconds()
            return left + (right - left) * (elapsed / span)

        for tick in range(6):
            fraction = tick / 5
            tick_x = left + (right - left) * fraction
            tick_time = start_time + (end_time - start_time) * fraction
            self.canvas.create_line(tick_x, top - 6, tick_x, bottom + 4, fill="#e5e5e5")
            self.canvas.create_text(
                tick_x,
                bottom + 16,
                text=tick_time.strftime("%H:%M:%S"),
                fill="#555555",
                font=("TkDefaultFont", 8),
            )

        for lane, idx in lane_index.items():
            station, task = lane
            y = top + idx * lane_height + lane_height / 2
            self.canvas.create_line(left, y, right, y, fill="#f0f0f0")
            self.canvas.create_text(
                left - 8,
                y,
                text=f"M{station} {_format_task_label(task, self.task_labels)}",
                anchor="e",
                font=("TkDefaultFont", 9, "bold"),
            )

        for event in self.events:
            y = top + lane_index[(event.station, event.task)] * lane_height + lane_height / 2
            x = x_for_time(event.execution_time)
            color = _progress_color(event.completion)
            radius = 5
            self.canvas.create_oval(
                x - radius,
                y - radius,
                x + radius,
                y + radius,
                fill=color,
                outline="#333333",
            )

        legend_markers = (-1.0, 0.0, 0.25, 0.5, 0.75, 1.0)
        for i, marker in enumerate(legend_markers):
            lx = right - 360 + i * 66
            ly = top - 14
            self.canvas.create_rectangle(
                lx, ly, lx + 12, ly + 12, fill=_progress_color(marker), outline="#333333"
            )
            self.canvas.create_text(
                lx + 16,
                ly + 6,
                text="no files" if marker == -1.0 else f"{marker:g}",
                anchor="w",
                font=("TkDefaultFont", 8),
            )

    def _fill_table(self) -> None:
        for item in self.table.get_children():
            self.table.delete(item)

        ordered = sorted(self.events, key=lambda item: item.execution_time, reverse=True)
        for event in ordered[: self.max_rows]:
            self.table.insert(
                "",
                "end",
                values=(
                    event.execution_time.strftime("%Y-%m-%d %H:%M:%S"),
                    f"MINGO0{event.station}",
                    _format_task_label(event.task, self.task_labels),
                    event.filename_base,
                    _completion_label(event.completion),
                    event.csv_mtime.strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Real-time STEP_1 status timeline GUI.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=get_repo_root(),
        help="Repository root (default: auto-detected).",
    )
    parser.add_argument(
        "--lookback-hours",
        type=float,
        default=0.5,
        help="Initial lookback window in hours.",
    )
    parser.add_argument(
        "--refresh-seconds",
        type=int,
        default=30,
        help="Auto-refresh interval in seconds.",
    )
    parser.add_argument(
        "--stations",
        default="all",
        help='Comma-separated station filter (e.g. "0,1") or "all".',
    )
    parser.add_argument(
        "--tasks",
        default="all",
        help='Comma-separated task filter (e.g. "0,1,2,3") or "all".',
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=250,
        help="Maximum number of rows shown in the table.",
    )
    parser.add_argument(
        "--snapshot",
        action="store_true",
        help="Print a terminal snapshot and exit (no GUI).",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    if args.snapshot:
        stations, station_error = _parse_id_filter(
            args.stations, min_value=0, max_value=4, label="station"
        )
        tasks, task_error = _parse_id_filter(
            args.tasks, min_value=0, max_value=5, label="task"
        )
        if station_error or task_error:
            print(station_error or task_error, file=sys.stderr)
            return 1
        events = load_status_events(
            args.repo_root.resolve(),
            now=datetime.now(),
            lookback=timedelta(hours=args.lookback_hours),
            station_filter=stations,
            task_filter=tasks,
        )
        task_labels = _load_task_labels(args.repo_root.resolve())
        print(f"status_rows={len(events)}")
        for event in events[-20:]:
            print(
                f"{event.execution_time:%Y-%m-%d %H:%M:%S} "
                f"M{event.station} {_format_task_label(event.task, task_labels)} {event.filename_base} "
                f"{_completion_label(event.completion)}"
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
    app = StatusTimelineApp(root, tk, ttk, args)
    del app
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
