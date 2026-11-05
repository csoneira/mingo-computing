#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/NOTIFICATIONS/STATUS_GUI/task2_calibration_timeline_gui.py
Purpose: Real-time TASK_2 calibration metadata timeline viewer (Tkinter, X11-friendly).
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-04-22
Runtime: python3
Usage: python3 CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/NOTIFICATIONS/STATUS_GUI/task2_calibration_timeline_gui.py [options]
Inputs: TASK_2 calibration metadata CSV files under PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO0*/...
Outputs: GUI or terminal snapshot.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

import argparse
import colorsys
import csv
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional


CALIBRATION_FILE_GLOB = (
    "PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO0*/STAGE_1/EVENT_DATA/STEP_1/TASK_2/METADATA/"
    "task_2_metadata_calibration.csv"
)
DATE_FORMATS = (
    "%Y-%m-%d_%H.%M.%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%d",
)
STATION_RE = re.compile(r"^MINGO0(\d)$")
COLUMN_RE = re.compile(r"^P([1-4])_s([1-4])_(Q_F|Q_B|T_sum|T_dif)$")
BASENAME_TIMESTAMP_PATTERN = re.compile(r"(?:^|[^0-9])(\d{11})(?:[^0-9]|$)")
FAMILY_ORDER = ("Q_F", "Q_B", "T_sum", "T_dif")
FAMILY_TITLES = {
    "Q_F": "Q_F calibration values",
    "Q_B": "Q_B calibration values",
    "T_sum": "T_sum calibration values",
    "T_dif": "T_dif calibration values",
}
X_MODE_EXECUTION = "execution_time"
X_MODE_BASENAME = "basename_time"
X_MODE_CHOICES = (X_MODE_EXECUTION, X_MODE_BASENAME)
X_MODE_LABELS = {
    X_MODE_EXECUTION: "Execution time",
    X_MODE_BASENAME: "Basename time",
}


@dataclass(frozen=True)
class CalibrationRow:
    station: int
    filename_base: str
    execution_time: datetime
    basename_time: Optional[datetime]
    csv_path: Path
    csv_mtime: datetime
    family_counts: dict[str, int]


@dataclass(frozen=True)
class CalibrationPoint:
    execution_time: datetime
    basename_time: Optional[datetime]
    filename_base: str
    value: float


@dataclass
class CalibrationSnapshot:
    rows: list[CalibrationRow]
    family_series: dict[str, dict[tuple[int, str], list[CalibrationPoint]]]


def _parse_datetime(value: object) -> Optional[datetime]:
    text = str(value).strip()
    if not text:
        return None

    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue

    iso_text = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(iso_text)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _parse_datetime_input(value: object, *, end_of_day: bool = False) -> Optional[datetime]:
    text = str(value).strip()
    if not text:
        return None
    parsed = _parse_datetime(text)
    if parsed is None:
        return None
    if len(text) == 10 and text.count("-") == 2 and end_of_day:
        return parsed + timedelta(days=1) - timedelta(seconds=1)
    return parsed


def _parse_float(value: object) -> Optional[float]:
    text = str(value).strip()
    if not text:
        return None
    try:
        numeric = float(text)
    except ValueError:
        return None
    if numeric != numeric:
        return None
    if numeric in (float("inf"), float("-inf")):
        return None
    return numeric


def _extract_station(path: Path) -> Optional[int]:
    for part in path.parts:
        match = STATION_RE.match(part)
        if match:
            return int(match.group(1))
    return None


def _iter_calibration_files(repo_root: Path) -> Iterable[Path]:
    yield from sorted(repo_root.glob(CALIBRATION_FILE_GLOB))


def normalize_basename(value: object) -> str:
    text = str(value).strip()
    if not text:
        return ""
    return Path(text).stem.strip()


def extract_timestamp_from_basename(value: object) -> Optional[datetime]:
    stem = normalize_basename(value)
    if not stem:
        return None

    try:
        return datetime.strptime(stem, "%Y-%m-%d_%H.%M.%S")
    except ValueError:
        pass

    match = BASENAME_TIMESTAMP_PATTERN.search(stem)
    if match:
        digits = match.group(1)
    else:
        compact = "".join(ch for ch in stem if ch.isdigit())
        if len(compact) < 11:
            return None
        digits = compact[-11:]

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
    if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
        return None

    base = datetime(year, 1, 1)
    return base + timedelta(
        days=day_of_year - 1,
        hours=hour,
        minutes=minute,
        seconds=second,
    )


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


def _column_sort_key(column_name: str) -> tuple[int, int, str]:
    match = COLUMN_RE.match(column_name)
    if not match:
        return (99, 99, column_name)
    plane = int(match.group(1))
    strip = int(match.group(2))
    return (plane, strip, column_name)


def _series_sort_key(series_key: tuple[int, str]) -> tuple[int, int, int, str]:
    station, column_name = series_key
    plane, strip, _ = _column_sort_key(column_name)
    return (station, plane, strip, column_name)


def _series_label(series_key: tuple[int, str], *, multi_station: bool) -> str:
    station, column_name = series_key
    if multi_station:
        return f"MINGO0{station}::{column_name}"
    return column_name


def _color_palette(count: int) -> list[str]:
    if count <= 0:
        return []
    colors: list[str] = []
    for idx in range(count):
        hue = idx / max(count, 1)
        red, green, blue = colorsys.hsv_to_rgb(hue, 0.72, 0.85)
        colors.append(f"#{int(red * 255):02x}{int(green * 255):02x}{int(blue * 255):02x}")
    return colors


def _format_tick(value: float) -> str:
    magnitude = abs(value)
    if magnitude >= 1000 or (magnitude > 0 and magnitude < 0.01):
        return f"{value:.2e}"
    if magnitude >= 100:
        return f"{value:.0f}"
    if magnitude >= 10:
        return f"{value:.1f}"
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _format_time_tick(moment: datetime, *, span_hours: float) -> str:
    if span_hours >= 48:
        return moment.strftime("%m-%d\n%H:%M")
    return moment.strftime("%H:%M:%S")


def load_calibration_snapshot(
    repo_root: Path,
    *,
    station_filter: Optional[set[int]] = None,
) -> CalibrationSnapshot:
    rows: list[CalibrationRow] = []
    family_series: dict[str, dict[tuple[int, str], list[CalibrationPoint]]] = {
        family: defaultdict(list) for family in FAMILY_ORDER
    }

    for csv_path in _iter_calibration_files(repo_root):
        station = _extract_station(csv_path)
        if station is None:
            continue
        if station_filter is not None and station not in station_filter:
            continue

        try:
            csv_mtime = datetime.fromtimestamp(csv_path.stat().st_mtime)
        except OSError:
            continue

        try:
            with csv_path.open(newline="") as handle:
                reader = csv.DictReader(handle)
                if not reader.fieldnames:
                    continue

                family_columns = {
                    family: sorted(
                        [
                            column_name
                            for column_name in reader.fieldnames
                            if COLUMN_RE.match(column_name)
                            and column_name.endswith(family)
                        ],
                        key=_column_sort_key,
                    )
                    for family in FAMILY_ORDER
                }

                for row in reader:
                    execution_value = (
                        row.get("execution_timestamp")
                        or row.get("execution_date")
                        or row.get("timestamp")
                        or ""
                    )
                    execution_time = _parse_datetime(execution_value)
                    if execution_time is None:
                        continue

                    filename_base = (
                        row.get("filename_base")
                        or row.get("basename")
                        or "<unknown>"
                    ).strip()
                    basename_time = extract_timestamp_from_basename(filename_base)

                    family_counts: dict[str, int] = {}
                    total_points = 0
                    for family in FAMILY_ORDER:
                        count = 0
                        for column_name in family_columns[family]:
                            numeric = _parse_float(row.get(column_name, ""))
                            if numeric is None:
                                continue
                            family_series[family][(station, column_name)].append(
                                CalibrationPoint(
                                    execution_time=execution_time,
                                    basename_time=basename_time,
                                    filename_base=filename_base,
                                    value=numeric,
                                )
                            )
                            count += 1
                        family_counts[family] = count
                        total_points += count

                    if total_points == 0:
                        continue

                    rows.append(
                        CalibrationRow(
                            station=station,
                            filename_base=filename_base,
                            execution_time=execution_time,
                            basename_time=basename_time,
                            csv_path=csv_path,
                            csv_mtime=csv_mtime,
                            family_counts=family_counts,
                        )
                    )
        except (OSError, csv.Error):
            continue

    rows.sort(key=lambda item: item.execution_time)
    for family_map in family_series.values():
        for points in family_map.values():
            points.sort(key=lambda item: item.execution_time)

    return CalibrationSnapshot(rows=rows, family_series=family_series)


class Task2CalibrationTimelineApp:
    def __init__(self, root, tk_module, ttk_module, args: argparse.Namespace) -> None:
        self.root = root
        self.tk = tk_module
        self.ttk = ttk_module
        self.repo_root = args.repo_root.resolve()
        self.max_rows = args.max_rows
        self.legend_limit = args.legend_limit
        self.after_id: Optional[str] = None
        self.snapshot = CalibrationSnapshot(
            rows=[],
            family_series={family: {} for family in FAMILY_ORDER},
        )
        self.visible_rows: list[CalibrationRow] = []
        self.current_x_mode = args.x_mode
        self.current_start_time: Optional[datetime] = None
        self.current_end_time: Optional[datetime] = None

        self.x_mode_var = self.tk.StringVar(value=args.x_mode)
        self.lookback_var = self.tk.StringVar(value=str(args.lookback_hours))
        self.basename_start_var = self.tk.StringVar(value=args.plot_start or "")
        self.basename_end_var = self.tk.StringVar(value=args.plot_end or "")
        self.refresh_var = self.tk.StringVar(value=str(args.refresh_seconds))
        self.station_var = self.tk.StringVar(value=args.stations)
        self.station_checkbuttons = [
            self.tk.BooleanVar(value=(i != 0))  # 0 unchecked, 1-4 checked
            for i in range(5)
        ]
        self.basename_lookback_var = self.tk.BooleanVar(value=args.basename_lookback)
        self.auto_refresh_var = self.tk.BooleanVar(value=True)
        self.show_legend_var = self.tk.BooleanVar(value=args.show_legend)
        self.status_var = self.tk.StringVar(value="Waiting for first refresh...")

        self._build_ui()
        self._refresh_now()

    def _build_ui(self) -> None:
        self.root.title("TASK_2 Calibration Timeline")
        self.root.geometry("1540x960")

        controls_top = self.ttk.Frame(self.root, padding=8)
        controls_top.pack(fill="x")

        self.ttk.Label(controls_top, text="X axis").pack(side="left")
        self.ttk.Radiobutton(
            controls_top,
            text="Execution Time",
            value=X_MODE_EXECUTION,
            variable=self.x_mode_var,
            command=self._on_x_mode_change,
        ).pack(side="left", padx=(6, 8))
        self.ttk.Radiobutton(
            controls_top,
            text="Basename Time",
            value=X_MODE_BASENAME,
            variable=self.x_mode_var,
            command=self._on_x_mode_change,
        ).pack(side="left", padx=(0, 12))

        self.ttk.Label(controls_top, text="Lookback (hours)").pack(side="left")
        self.ttk.Entry(controls_top, width=8, textvariable=self.lookback_var).pack(
            side="left", padx=(4, 12)
        )

        self.ttk.Label(controls_top, text="Refresh (s)").pack(side="left")
        self.ttk.Entry(controls_top, width=6, textvariable=self.refresh_var).pack(
            side="left", padx=(4, 12)
        )

        self.ttk.Label(controls_top, text="Stations").pack(side="left")
        stations_frame = self.ttk.Frame(controls_top)
        stations_frame.pack(side="left", padx=(4, 12))
        for i in range(5):
            self.ttk.Checkbutton(
                stations_frame,
                text=f"MINGO0{i}",
                variable=self.station_checkbuttons[i],
                command=self._refresh_now,
            ).pack(side="left", padx=2)

        self.ttk.Checkbutton(
            controls_top,
            text="Auto Refresh",
            variable=self.auto_refresh_var,
        ).pack(side="left", padx=(0, 12))

        self.ttk.Checkbutton(
            controls_top,
            text="Show Legend",
            variable=self.show_legend_var,
            command=self._draw_timeline,
        ).pack(side="left", padx=(0, 12))

        self.ttk.Button(controls_top, text="Refresh Now", command=self._refresh_now).pack(
            side="left"
        )

        controls_bottom = self.ttk.Frame(self.root, padding=(8, 0, 8, 8))
        controls_bottom.pack(fill="x")

        self.ttk.Label(controls_bottom, text="Plot Start").pack(side="left")
        self.ttk.Entry(
            controls_bottom,
            width=20,
            textvariable=self.basename_start_var,
        ).pack(side="left", padx=(4, 12))

        self.ttk.Label(controls_bottom, text="Plot End").pack(side="left")
        self.ttk.Entry(
            controls_bottom,
            width=20,
            textvariable=self.basename_end_var,
        ).pack(side="left", padx=(4, 12))

        self.ttk.Button(
            controls_bottom,
            text="Use Data Limits",
            command=self._set_basename_range_to_data_limits,
        ).pack(side="left", padx=(0, 12))

        self.ttk.Checkbutton(
            controls_bottom,
            text="Use Lookback For Basename",
            variable=self.basename_lookback_var,
            command=self._refresh_now,
        ).pack(side="left", padx=(0, 12))

        self.ttk.Label(
            controls_bottom,
            text="Datetime format: YYYY-MM-DD or YYYY-MM-DD HH:MM:SS",
        ).pack(side="left")

        self.canvas = self.tk.Canvas(self.root, bg="white", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.canvas.bind("<Configure>", lambda _event: self._draw_timeline())

        table_frame = self.ttk.Frame(self.root, padding=(8, 0, 8, 8))
        table_frame.pack(fill="both", expand=False)

        columns = (
            "execution",
            "station",
            "file",
            "q_f",
            "q_b",
            "t_sum",
            "t_dif",
            "source_mtime",
        )
        self.table = self.ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            height=11,
        )
        self.table.heading("execution", text="Execution Time")
        self.table.heading("station", text="Station")
        self.table.heading("file", text="Filename Base")
        self.table.heading("q_f", text="Q_F")
        self.table.heading("q_b", text="Q_B")
        self.table.heading("t_sum", text="T_sum")
        self.table.heading("t_dif", text="T_dif")
        self.table.heading("source_mtime", text="CSV Last Modified")
        self.table.column("execution", width=170, anchor="w")
        self.table.column("station", width=70, anchor="center")
        self.table.column("file", width=270, anchor="w")
        self.table.column("q_f", width=70, anchor="center")
        self.table.column("q_b", width=70, anchor="center")
        self.table.column("t_sum", width=70, anchor="center")
        self.table.column("t_dif", width=70, anchor="center")
        self.table.column("source_mtime", width=170, anchor="w")

        scrollbar = self.ttk.Scrollbar(
            table_frame, orient="vertical", command=self.table.yview
        )
        self.table.configure(yscrollcommand=scrollbar.set)
        self.table.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="left", fill="y")

        status_bar = self.ttk.Label(
            self.root,
            textvariable=self.status_var,
            anchor="w",
            padding=(8, 0, 8, 8),
        )
        status_bar.pack(fill="x")

    def _get_selected_stations_str(self) -> str:
        """Get selected stations as comma-separated string for _parse_id_filter."""
        selected = [str(i) for i in range(5) if self.station_checkbuttons[i].get()]
        return ",".join(selected) if selected else "0,1,2,3,4"

    def _read_filters(self) -> tuple[Optional[dict[str, object]], Optional[str]]:
        try:
            refresh_seconds = int(self.refresh_var.get())
        except ValueError:
            return None, "Refresh must be numeric."

        if refresh_seconds <= 0:
            return None, "Refresh must be > 0 seconds."

        x_mode = self.x_mode_var.get().strip()
        if x_mode not in X_MODE_CHOICES:
            return None, f"Invalid X mode: {x_mode}"

        lookback_hours: Optional[float] = None
        if x_mode == X_MODE_EXECUTION or (x_mode == X_MODE_BASENAME and self.basename_lookback_var.get()):
            try:
                lookback_hours = float(self.lookback_var.get())
            except ValueError:
                return None, "Lookback must be numeric."
            if lookback_hours <= 0:
                return None, "Lookback must be > 0 hours."

        plot_start: Optional[datetime] = None
        plot_end: Optional[datetime] = None
        if x_mode == X_MODE_BASENAME:
            start_text = self.basename_start_var.get().strip()
            end_text = self.basename_end_var.get().strip()
            if start_text:
                plot_start = _parse_datetime_input(start_text, end_of_day=False)
                if plot_start is None:
                    return None, f"Invalid plot start: {start_text}"
            if end_text:
                plot_end = _parse_datetime_input(end_text, end_of_day=True)
                if plot_end is None:
                    return None, f"Invalid plot end: {end_text}"

        stations, station_error = _parse_id_filter(
            self._get_selected_stations_str(),
            min_value=0,
            max_value=4,
            label="station",
        )
        if station_error:
            return None, station_error

        return (
            {
                "x_mode": x_mode,
                "lookback_hours": lookback_hours,
                "basename_lookback": self.basename_lookback_var.get(),
                "plot_start": plot_start,
                "plot_end": plot_end,
                "refresh_seconds": refresh_seconds,
                "stations": stations,
            },
            None,
        )

    def _on_x_mode_change(self) -> None:
        if self.x_mode_var.get() == X_MODE_BASENAME:
            self._set_basename_range_to_data_limits(refresh=False)
        self._refresh_now()

    def _row_x_time(self, row: CalibrationRow, x_mode: str) -> Optional[datetime]:
        if x_mode == X_MODE_BASENAME:
            return row.basename_time
        return row.execution_time

    def _point_x_time(self, point: CalibrationPoint, x_mode: str) -> Optional[datetime]:
        if x_mode == X_MODE_BASENAME:
            return point.basename_time
        return point.execution_time

    def _available_time_limits(
        self,
        x_mode: str,
    ) -> tuple[Optional[datetime], Optional[datetime]]:
        times = [
            self._row_x_time(row, x_mode)
            for row in self.snapshot.rows
        ]
        valid_times = [moment for moment in times if moment is not None]
        if not valid_times:
            return None, None
        return min(valid_times), max(valid_times)

    def _set_basename_range_to_data_limits(self, refresh: bool = True) -> None:
        start_time, end_time = self._available_time_limits(X_MODE_BASENAME)
        if start_time is None or end_time is None:
            if refresh:
                self._refresh_now()
            return
        self.basename_start_var.set(start_time.strftime("%Y-%m-%d %H:%M:%S"))
        self.basename_end_var.set(end_time.strftime("%Y-%m-%d %H:%M:%S"))
        if refresh:
            self._refresh_now()

    def _resolve_plot_window(
        self,
        config: dict[str, object],
        now: datetime,
    ) -> tuple[Optional[datetime], Optional[datetime], Optional[str]]:
        x_mode = str(config["x_mode"])
        if x_mode == X_MODE_EXECUTION:
            lookback_hours = float(config["lookback_hours"])
            return now - timedelta(hours=lookback_hours), now, None

        available_start, available_end = self._available_time_limits(X_MODE_BASENAME)
        if available_start is None or available_end is None:
            return None, None, "No basename timestamps available in the current station selection."

        if bool(config.get("basename_lookback")):
            lookback_hours = float(config["lookback_hours"])
            start_time = available_end - timedelta(hours=lookback_hours)
            return max(start_time, available_start), available_end, None

        start_time = config["plot_start"] if config["plot_start"] is not None else available_start
        end_time = config["plot_end"] if config["plot_end"] is not None else available_end
        if config["plot_start"] is None and not self.basename_start_var.get().strip():
            self.basename_start_var.set(start_time.strftime("%Y-%m-%d %H:%M:%S"))
        if config["plot_end"] is None and not self.basename_end_var.get().strip():
            self.basename_end_var.set(end_time.strftime("%Y-%m-%d %H:%M:%S"))
        if start_time > end_time:
            return None, None, "Plot start must be <= plot end."
        return start_time, end_time, None

    def _schedule_next(self, refresh_seconds: int) -> None:
        if not self.auto_refresh_var.get():
            return
        self.after_id = self.root.after(refresh_seconds * 1000, self._refresh_now)

    def _refresh_now(self) -> None:
        if self.after_id is not None:
            self.root.after_cancel(self.after_id)
            self.after_id = None

        config, error = self._read_filters()
        if error is not None:
            self.visible_rows = []
            self.current_start_time = None
            self.current_end_time = None
            self.status_var.set(f"Configuration error: {error}")
            self._draw_timeline()
            self._fill_table()
            self._schedule_next(5)
            return

        assert config is not None
        now = datetime.now()
        self.snapshot = load_calibration_snapshot(
            self.repo_root,
            station_filter=config["stations"],
        )
        start_time, end_time, window_error = self._resolve_plot_window(config, now)
        if window_error is not None or start_time is None or end_time is None:
            self.current_x_mode = str(config["x_mode"])
            self.current_start_time = None
            self.current_end_time = None
            self.visible_rows = []
            self.status_var.set(f"Configuration error: {window_error}")
            self._draw_timeline()
            self._fill_table()
            self._schedule_next(int(config["refresh_seconds"]))
            return

        self.current_x_mode = str(config["x_mode"])
        self.current_start_time = start_time
        self.current_end_time = end_time
        self.visible_rows = [
            row
            for row in self.snapshot.rows
            if (self._row_x_time(row, self.current_x_mode) is not None)
            and start_time <= self._row_x_time(row, self.current_x_mode) <= end_time
        ]

        self._draw_timeline()
        self._fill_table()

        latest = (
            max(
                self._row_x_time(row, self.current_x_mode)
                for row in self.visible_rows
                if self._row_x_time(row, self.current_x_mode) is not None
            ).strftime("%Y-%m-%d %H:%M:%S")
            if self.visible_rows
            else "-"
        )
        time_window_text = f"{start_time:%Y-%m-%d %H:%M:%S} -> {end_time:%Y-%m-%d %H:%M:%S}"
        family_summary = " | ".join(
            (
                f"{family}={len(self.snapshot.family_series.get(family, {}))} series/"
                f"{sum(len(points) for points in self.snapshot.family_series.get(family, {}).values())} total points"
            )
            for family in FAMILY_ORDER
        )
        self.status_var.set(
            f"Visible rows: {len(self.visible_rows)} / Total rows: {len(self.snapshot.rows)} | "
            f"{family_summary} | X mode: {X_MODE_LABELS[self.current_x_mode]} | "
            f"Window: {time_window_text} | Latest visible: {latest} | "
            f"Last refresh: {now.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        self._schedule_next(int(config["refresh_seconds"]))

    def _draw_timeline(self) -> None:
        self.canvas.delete("all")
        width = max(self.canvas.winfo_width(), 900)
        height = max(self.canvas.winfo_height(), 420)

        if self.current_start_time is None or self.current_end_time is None:
            self.canvas.create_text(
                width // 2,
                height // 2,
                text="Refresh the view with a valid time window.",
                fill="#444444",
                font=("TkDefaultFont", 12, "bold"),
            )
            return

        if not self.visible_rows:
            self.canvas.create_text(
                width // 2,
                height // 2,
                text="No calibration rows in the selected time window.",
                fill="#444444",
                font=("TkDefaultFont", 12, "bold"),
            )
            return

        start_time = self.current_start_time
        end_time = self.current_end_time
        span_hours = max((end_time - start_time).total_seconds() / 3600.0, 0.001)

        margin_left = 18
        margin_right = 18
        margin_top = 16
        margin_bottom = 20
        gap_x = 14
        gap_y = 14
        panel_width = (width - margin_left - margin_right - gap_x) / 2.0
        panel_height = (height - margin_top - margin_bottom - gap_y) / 2.0

        selected_stations, _ = _parse_id_filter(
            self._get_selected_stations_str(),
            min_value=0,
            max_value=4,
            label="station",
        )
        multi_station = selected_stations is None or len(selected_stations) != 1

        for index, family in enumerate(FAMILY_ORDER):
            row_index = index // 2
            col_index = index % 2
            panel_left = margin_left + col_index * (panel_width + gap_x)
            panel_top = margin_top + row_index * (panel_height + gap_y)
            panel_right = panel_left + panel_width
            panel_bottom = panel_top + panel_height
            self._draw_family_panel(
                family=family,
                panel_left=panel_left,
                panel_top=panel_top,
                panel_right=panel_right,
                panel_bottom=panel_bottom,
                start_time=start_time,
                end_time=end_time,
                span_hours=span_hours,
                multi_station=multi_station,
            )

    def _draw_family_panel(
        self,
        *,
        family: str,
        panel_left: float,
        panel_top: float,
        panel_right: float,
        panel_bottom: float,
        start_time: datetime,
        end_time: datetime,
        span_hours: float,
        multi_station: bool,
    ) -> None:
        self.canvas.create_rectangle(
            panel_left,
            panel_top,
            panel_right,
            panel_bottom,
            outline="#d0d0d0",
            fill="#fcfcfc",
        )

        family_map = self.snapshot.family_series.get(family, {})
        title = FAMILY_TITLES[family]
        total_points = sum(len(points) for points in family_map.values())
        self.canvas.create_text(
            panel_left + 10,
            panel_top + 10,
            anchor="nw",
            text=f"{title} | {len(family_map)} series | {total_points} points",
            font=("TkDefaultFont", 10, "bold"),
            fill="#222222",
        )

        if not family_map:
            self.canvas.create_text(
                (panel_left + panel_right) / 2,
                (panel_top + panel_bottom) / 2,
                text="No points for this family.",
                fill="#666666",
                font=("TkDefaultFont", 11),
            )
            return

        show_legend = self.show_legend_var.get() and len(family_map) <= self.legend_limit
        legend_width = 180 if show_legend else 0
        plot_left = panel_left + 56
        plot_right = panel_right - 12 - legend_width
        plot_top = panel_top + 30
        plot_bottom = panel_bottom - 32

        if plot_right - plot_left < 80:
            plot_right = panel_right - 12
            legend_width = 0
            show_legend = False

        values = [
            point.value
            for points in family_map.values()
            for point in points
            if (
                self._point_x_time(point, self.current_x_mode) is not None
                and start_time <= self._point_x_time(point, self.current_x_mode) <= end_time
            )
        ]
        if not values:
            self.canvas.create_text(
                (panel_left + panel_right) / 2,
                (panel_top + panel_bottom) / 2,
                text="No points for this family in the current time window.",
                fill="#666666",
                font=("TkDefaultFont", 11),
            )
            return

        y_min = min(values)
        y_max = max(values)
        if abs(y_max - y_min) < 1e-12:
            pad = max(abs(y_max), 1.0) * 0.05
            y_min -= pad
            y_max += pad
        else:
            pad = (y_max - y_min) * 0.05
            y_min -= pad
            y_max += pad

        x_span = max((end_time - start_time).total_seconds(), 1.0)
        y_span = max(y_max - y_min, 1e-12)

        def x_for_time(moment: datetime) -> float:
            elapsed = (moment - start_time).total_seconds()
            return plot_left + (plot_right - plot_left) * (elapsed / x_span)

        def y_for_value(value: float) -> float:
            fraction = (value - y_min) / y_span
            return plot_bottom - (plot_bottom - plot_top) * fraction

        for tick in range(6):
            fraction = tick / 5.0
            tick_x = plot_left + (plot_right - plot_left) * fraction
            tick_time = start_time + (end_time - start_time) * fraction
            self.canvas.create_line(
                tick_x,
                plot_top,
                tick_x,
                plot_bottom,
                fill="#ebebeb",
            )
            self.canvas.create_text(
                tick_x,
                plot_bottom + 14,
                text=_format_time_tick(tick_time, span_hours=span_hours),
                fill="#555555",
                font=("TkDefaultFont", 7),
            )

        for tick in range(5):
            fraction = tick / 4.0
            value = y_min + (y_max - y_min) * fraction
            tick_y = plot_bottom - (plot_bottom - plot_top) * fraction
            self.canvas.create_line(
                plot_left,
                tick_y,
                plot_right,
                tick_y,
                fill="#ebebeb",
            )
            self.canvas.create_text(
                plot_left - 6,
                tick_y,
                anchor="e",
                text=_format_tick(value),
                fill="#555555",
                font=("TkDefaultFont", 8),
            )

        self.canvas.create_rectangle(
            plot_left,
            plot_top,
            plot_right,
            plot_bottom,
            outline="#b8b8b8",
        )

        sorted_series = sorted(family_map.items(), key=lambda item: _series_sort_key(item[0]))
        palette = _color_palette(len(sorted_series))
        legend_entries: list[tuple[str, str]] = []

        for index, (series_key, points) in enumerate(sorted_series):
            coords: list[float] = []
            visible_points = [
                point
                for point in points
                if (
                    self._point_x_time(point, self.current_x_mode) is not None
                    and start_time <= self._point_x_time(point, self.current_x_mode) <= end_time
                )
            ]
            visible_points.sort(
                key=lambda point: self._point_x_time(point, self.current_x_mode) or datetime.min
            )
            if not visible_points:
                continue
            for point in visible_points:
                moment = self._point_x_time(point, self.current_x_mode)
                assert moment is not None
                coords.extend((x_for_time(moment), y_for_value(point.value)))
            color = palette[index]
            if len(coords) >= 4:
                self.canvas.create_line(*coords, fill=color, width=1.6, smooth=False)
            last_x = coords[-2]
            last_y = coords[-1]
            self.canvas.create_oval(
                last_x - 2.2,
                last_y - 2.2,
                last_x + 2.2,
                last_y + 2.2,
                fill=color,
                outline=color,
            )
            legend_entries.append((_series_label(series_key, multi_station=multi_station), color))

        if show_legend:
            legend_left = plot_right + 12
            legend_top = plot_top
            self.canvas.create_text(
                legend_left,
                legend_top,
                anchor="nw",
                text="Series",
                font=("TkDefaultFont", 9, "bold"),
                fill="#333333",
            )
            item_height = 13
            items_per_column = max(int((plot_bottom - legend_top - 16) // item_height), 1)
            legend_column_width = 86
            for index, (label, color) in enumerate(legend_entries):
                col_idx = index // items_per_column
                row_idx = index % items_per_column
                item_x = legend_left + col_idx * legend_column_width
                item_y = legend_top + 14 + row_idx * item_height
                self.canvas.create_line(
                    item_x,
                    item_y + 5,
                    item_x + 12,
                    item_y + 5,
                    fill=color,
                    width=2,
                )
                self.canvas.create_text(
                    item_x + 16,
                    item_y + 5,
                    anchor="w",
                    text=label,
                    font=("TkDefaultFont", 7),
                    fill="#222222",
                )
        elif self.show_legend_var.get() and len(family_map) > self.legend_limit:
            self.canvas.create_text(
                panel_right - 10,
                panel_top + 12,
                anchor="ne",
                text=f"Legend hidden ({len(family_map)} > {self.legend_limit})",
                font=("TkDefaultFont", 8),
                fill="#666666",
            )

    def _fill_table(self) -> None:
        for item in self.table.get_children():
            self.table.delete(item)

        self.table.heading(
            "execution",
            text="Basename Time" if self.current_x_mode == X_MODE_BASENAME else "Execution Time",
        )
        ordered = sorted(
            self.visible_rows,
            key=lambda item: self._row_x_time(item, self.current_x_mode) or datetime.min,
            reverse=True,
        )
        for row in ordered[: self.max_rows]:
            row_time = self._row_x_time(row, self.current_x_mode)
            self.table.insert(
                "",
                "end",
                values=(
                    row_time.strftime("%Y-%m-%d %H:%M:%S") if row_time is not None else "-",
                    f"MINGO0{row.station}",
                    row.filename_base,
                    row.family_counts.get("Q_F", 0),
                    row.family_counts.get("Q_B", 0),
                    row.family_counts.get("T_sum", 0),
                    row.family_counts.get("T_dif", 0),
                    row.csv_mtime.strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Real-time TASK_2 calibration metadata timeline GUI."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[4],
        help="Repository root (default: auto-detected).",
    )
    parser.add_argument(
        "--x-mode",
        choices=X_MODE_CHOICES,
        default=X_MODE_EXECUTION,
        help="X-axis mode: execution time or basename-derived time.",
    )
    parser.add_argument(
        "--lookback-hours",
        type=float,
        default=12.0,
        help="Initial lookback window in hours for execution-time mode.",
    )
    parser.add_argument(
        "--plot-start",
        default="",
        help="Plot start datetime for basename-time mode.",
    )
    parser.add_argument(
        "--plot-end",
        default="",
        help="Plot end datetime for basename-time mode.",
    )
    parser.add_argument(
        "--basename-lookback",
        action="store_true",
        help="In basename-time mode, use the lookback window ending at the freshest basename time.",
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
        help='Comma-separated station filter (e.g. "1,2") or "all".',
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=250,
        help="Maximum number of rows shown in the table.",
    )
    parser.add_argument(
        "--legend-limit",
        type=int,
        default=16,
        help="Show per-panel legend only when series count is <= this value.",
    )
    parser.add_argument(
        "--show-legend",
        action="store_true",
        help="Enable legends on startup when series count is small enough.",
    )
    parser.add_argument(
        "--snapshot",
        action="store_true",
        help="Print a terminal snapshot and exit (no GUI).",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv or sys.argv[1:])

    stations, station_error = _parse_id_filter(
        args.stations,
        min_value=0,
        max_value=4,
        label="station",
    )
    if station_error:
        print(station_error, file=sys.stderr)
        return 1

    now = datetime.now()
    snapshot = load_calibration_snapshot(
        args.repo_root.resolve(),
        station_filter=stations,
    )

    if args.x_mode == X_MODE_EXECUTION:
        if args.lookback_hours <= 0:
            print("Lookback must be > 0 hours.", file=sys.stderr)
            return 1
        start_time = now - timedelta(hours=args.lookback_hours)
        end_time = now
    else:
        basename_times = [row.basename_time for row in snapshot.rows if row.basename_time is not None]
        if not basename_times:
            print("No basename timestamps available in the selected station set.", file=sys.stderr)
            return 1
        if args.basename_lookback:
            if args.lookback_hours <= 0:
                print("Lookback must be > 0 hours.", file=sys.stderr)
                return 1
            end_time = max(basename_times)
            start_time = max(min(basename_times), end_time - timedelta(hours=args.lookback_hours))
        else:
            start_time = (
                _parse_datetime_input(args.plot_start, end_of_day=False)
                if args.plot_start.strip()
                else min(basename_times)
            )
            end_time = (
                _parse_datetime_input(args.plot_end, end_of_day=True)
                if args.plot_end.strip()
                else max(basename_times)
            )
            if start_time is None:
                print(f"Invalid plot start: {args.plot_start}", file=sys.stderr)
                return 1
            if end_time is None:
                print(f"Invalid plot end: {args.plot_end}", file=sys.stderr)
                return 1
            if start_time > end_time:
                print("Plot start must be <= plot end.", file=sys.stderr)
                return 1

    visible_rows = [
        row
        for row in snapshot.rows
        if (
            (row.basename_time if args.x_mode == X_MODE_BASENAME else row.execution_time)
            is not None
        )
        and start_time
        <= (row.basename_time if args.x_mode == X_MODE_BASENAME else row.execution_time)
        <= end_time
    ]

    if args.snapshot:
        print(f"rows={len(visible_rows)}")
        print(f"x_mode={args.x_mode}")
        print(f"window_start={start_time:%Y-%m-%d %H:%M:%S}")
        print(f"window_end={end_time:%Y-%m-%d %H:%M:%S}")
        for family in FAMILY_ORDER:
            family_map = snapshot.family_series.get(family, {})
            print(
                f"{family}_series={len(family_map)} "
                f"{family}_points={sum(len(points) for points in family_map.values())}"
            )
        ordered_rows = sorted(
            visible_rows,
            key=lambda row: (
                row.basename_time if args.x_mode == X_MODE_BASENAME else row.execution_time
            ) or datetime.min,
        )
        for row in ordered_rows[-20:]:
            row_time = row.basename_time if args.x_mode == X_MODE_BASENAME else row.execution_time
            print(
                f"{row_time:%Y-%m-%d %H:%M:%S} "
                f"MINGO0{row.station} {row.filename_base} "
                f"Q_F={row.family_counts.get('Q_F', 0)} "
                f"Q_B={row.family_counts.get('Q_B', 0)} "
                f"T_sum={row.family_counts.get('T_sum', 0)} "
                f"T_dif={row.family_counts.get('T_dif', 0)}"
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
    app = Task2CalibrationTimelineApp(root, tk, ttk, args)
    del app
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
