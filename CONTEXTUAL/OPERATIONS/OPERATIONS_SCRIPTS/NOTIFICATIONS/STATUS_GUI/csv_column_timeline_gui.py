#!/usr/bin/env python3

"""Generic CSV timeline GUI with selectable Y column and X-axis mode."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

_REPO_IMPORT_ROOT = Path(__file__).resolve().parents[5]
if str(_REPO_IMPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_IMPORT_ROOT))
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.path_config import get_repo_root

from typing import Optional

DEFAULT_CONFIG_FILENAME = "csv_column_timeline_gui_config.json"

X_MODE_RECORD_TIME = "record_time"
X_MODE_BASENAME_TIME = "basename_time"
X_MODE_CHOICES = (X_MODE_RECORD_TIME, X_MODE_BASENAME_TIME)
X_MODE_LABELS = {
    X_MODE_RECORD_TIME: "Current/record time",
    X_MODE_BASENAME_TIME: "Basename time",
}

DATE_FORMATS = (
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d_%H.%M.%S",
    "%Y/%m/%d %H:%M:%S",
)

BASENAME_TIMESTAMP_DIGITS = 11
FILENAME_TIMESTAMP_PATTERN = re.compile(r"(?:^|[^0-9])(\d{11})(?:[^0-9]|$)")
HEADER_KEYWORDS = (
    "timestamp",
    "date",
    "time",
    "execution",
    "basename",
    "filename",
    "station",
    "task",
    "step",
    "status",
)

TIMESTAMP_COLUMN_PRIORITY = (
    "timestamp_utc",
    "execution_timestamp_utc",
    "execution_timestamp",
    "execution_date",
    "timestamp",
    "plot_timestamp",
    "file_timestamp",
    "datetime",
    "date_time",
    "date",
    "time",
)

BASENAME_COLUMN_PRIORITY = (
    "filename_base",
    "basename",
    "filename",
    "file",
    "path",
    "filepath",
)

DEFAULT_CONFIG = {
    "startup_csv_path": "",
    "startup_y_column": "",
    "startup_x_mode": X_MODE_RECORD_TIME,
    "startup_lookback_hours": 24.0,
    "startup_refresh_seconds": 30,
    "recent_csv_paths": [],
}

DEFAULT_CSV_REL = (
    "PIPELINE/MINGO_DIGITAL_TWIN/PLOTTERS/EXECUTION/SIMULATION_TIME/"
    "simulation_execution_times.csv"
)


@dataclass(frozen=True)
class CsvPoint:
    x_time: datetime
    y_value: float
    row_number: int
    basename: str


def _utc_now_naive() -> datetime:
    """Return current UTC time as a naive datetime for consistent comparisons."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _dedupe_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        candidate = value.strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        ordered.append(candidate)
    return ordered


def _parse_float(value: object) -> Optional[float]:
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _parse_datetime(value: object) -> Optional[datetime]:
    text = str(value).strip()
    if not text:
        return None

    for fmt in DATE_FORMATS:
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed
        except ValueError:
            continue

    # ISO fallback (including timezone-aware values)
    iso_text = text.replace("Z", "+00:00")
    try:
        parsed_iso = datetime.fromisoformat(iso_text)
        if parsed_iso.tzinfo is not None:
            parsed_iso = parsed_iso.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed_iso
    except ValueError:
        pass

    numeric = _parse_float(text)
    if numeric is not None:
        # Heuristic: very large values likely represent milliseconds.
        if numeric > 10_000_000_000:
            numeric = numeric / 1000.0
        try:
            return datetime.utcfromtimestamp(numeric)
        except (OverflowError, OSError, ValueError):
            return None

    return None


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

    match = FILENAME_TIMESTAMP_PATTERN.search(stem)
    if match:
        digits = match.group(1)
    else:
        compact = "".join(ch for ch in stem if ch.isdigit())
        if len(compact) < BASENAME_TIMESTAMP_DIGITS:
            return None
        digits = compact[-BASENAME_TIMESTAMP_DIGITS:]

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


def _looks_like_header(first_row: list[str]) -> bool:
    if not first_row:
        return False

    keyword_hits = 0
    alpha_cells = 0
    numeric_cells = 0

    for cell in first_row:
        text = str(cell).strip()
        lowered = text.lower()
        if any(keyword in lowered for keyword in HEADER_KEYWORDS):
            keyword_hits += 1
        if any(ch.isalpha() for ch in text):
            alpha_cells += 1
        if _parse_float(text) is not None:
            numeric_cells += 1

    if keyword_hits > 0:
        return True
    if alpha_cells == 0:
        return False

    return alpha_cells >= max(1, len(first_row) // 2) and numeric_cells <= len(first_row) // 2


def _clean_header_names(row: list[str]) -> list[str]:
    names: list[str] = []
    used: dict[str, int] = {}

    for idx, cell in enumerate(row):
        raw = str(cell).strip()
        name = re.sub(r"\s+", "_", raw) if raw else f"col_{idx + 1}"
        if not name:
            name = f"col_{idx + 1}"
        count = used.get(name, 0)
        if count > 0:
            unique_name = f"{name}_{count + 1}"
        else:
            unique_name = name
        used[name] = count + 1
        names.append(unique_name)

    return names


def _ensure_field_count(fieldnames: list[str], count: int) -> None:
    while len(fieldnames) < count:
        fieldnames.append(f"col_{len(fieldnames) + 1}")


def _row_to_dict(raw_row: list[str], fieldnames: list[str]) -> dict[str, str]:
    _ensure_field_count(fieldnames, len(raw_row))
    result: dict[str, str] = {}
    for idx, name in enumerate(fieldnames):
        result[name] = raw_row[idx].strip() if idx < len(raw_row) else ""
    return result


def prepare_csv_layout(csv_path: Path, sample_rows: int = 500) -> tuple[list[str], bool]:
    if not csv_path.exists():
        return [], False

    try:
        with csv_path.open(newline="") as handle:
            reader = csv.reader(handle)
            first_row = next(reader, None)
            if first_row is None:
                return [], False

            has_header = _looks_like_header(first_row)
            if has_header:
                fieldnames = _clean_header_names(first_row)
            else:
                fieldnames = [f"col_{idx + 1}" for idx in range(len(first_row))]

            max_cols = len(first_row)
            scanned = 0
            for row in reader:
                if len(row) > max_cols:
                    max_cols = len(row)
                scanned += 1
                if scanned >= sample_rows:
                    break

            _ensure_field_count(fieldnames, max_cols)
            return fieldnames, has_header
    except (OSError, csv.Error):
        return [], False


def iter_csv_rows(
    csv_path: Path,
    fieldnames: list[str],
    has_header: bool,
) -> tuple[int, dict[str, str]]:
    try:
        with csv_path.open(newline="") as handle:
            reader = csv.reader(handle)
            first_row = next(reader, None)
            if first_row is None:
                return

            row_number = 0
            if not has_header:
                row_number += 1
                yield row_number, _row_to_dict(first_row, fieldnames)

            for row in reader:
                row_number += 1
                if not row:
                    continue
                yield row_number, _row_to_dict(row, fieldnames)
    except (OSError, csv.Error):
        return


def detect_numeric_columns(
    csv_path: Path,
    fieldnames: list[str],
    has_header: bool,
    sample_rows: int = 1000,
) -> list[str]:
    seen: dict[str, int] = {name: 0 for name in fieldnames}
    numeric: dict[str, int] = {name: 0 for name in fieldnames}

    for row_number, row in iter_csv_rows(csv_path, fieldnames, has_header):
        if row_number > sample_rows:
            break
        for name in fieldnames:
            value = row.get(name, "").strip()
            if not value:
                continue
            seen[name] += 1
            if _parse_float(value) is not None:
                numeric[name] += 1

    result: list[str] = []
    for name in fieldnames:
        if seen[name] == 0:
            continue
        ratio = numeric[name] / seen[name]
        if ratio >= 0.6:
            result.append(name)
    return result


def _detect_timestamp_columns(fieldnames: list[str]) -> list[str]:
    lower_to_name = {name.lower(): name for name in fieldnames}
    selected: list[str] = []

    for candidate in TIMESTAMP_COLUMN_PRIORITY:
        if candidate in lower_to_name:
            selected.append(lower_to_name[candidate])

    for name in fieldnames:
        lowered = name.lower()
        if name in selected:
            continue
        if "time" in lowered or "date" in lowered:
            selected.append(name)

    return selected


def _detect_basename_columns(fieldnames: list[str]) -> list[str]:
    lower_to_name = {name.lower(): name for name in fieldnames}
    selected: list[str] = []

    for candidate in BASENAME_COLUMN_PRIORITY:
        if candidate in lower_to_name:
            selected.append(lower_to_name[candidate])

    for name in fieldnames:
        lowered = name.lower()
        if name in selected:
            continue
        if "basename" in lowered or "filename" in lowered or lowered.endswith("_base"):
            selected.append(name)

    return selected


def _pick_basename(row: dict[str, str], basename_columns: list[str]) -> str:
    for name in basename_columns:
        value = row.get(name, "").strip()
        if value:
            return normalize_basename(value)

    # Fallback for generic CSVs without basename-like headers.
    for value in row.values():
        candidate = normalize_basename(value)
        if candidate and extract_timestamp_from_basename(candidate) is not None:
            return candidate
    return ""


def _pick_timestamp(
    row: dict[str, str],
    timestamp_columns: list[str],
) -> Optional[datetime]:
    for name in timestamp_columns:
        value = row.get(name, "").strip()
        if not value:
            continue
        parsed = _parse_datetime(value)
        if parsed is not None:
            return parsed

    # Fallback for generic CSVs without timestamp-like headers.
    for name, value in row.items():
        if name in timestamp_columns:
            continue
        parsed = _parse_datetime(value)
        if parsed is not None:
            return parsed
    return None


def _default_y_column(fieldnames: list[str], numeric_columns: list[str]) -> Optional[str]:
    if not fieldnames:
        return None

    lower_to_name = {name.lower(): name for name in fieldnames}
    preferred = (
        "exec_time_s",
        "duration",
        "value",
        "completion_fraction",
        "rate_hz",
        "count",
    )
    for candidate in preferred:
        real_name = lower_to_name.get(candidate)
        if real_name and real_name in numeric_columns:
            return real_name

    if numeric_columns:
        return numeric_columns[0]
    return fieldnames[0]


def collect_series_points(
    csv_path: Path,
    *,
    fieldnames: list[str],
    has_header: bool,
    y_column: str,
    x_mode: str,
    lookback: timedelta,
    now_utc: Optional[datetime] = None,
) -> tuple[list[CsvPoint], dict[str, int]]:
    now = now_utc or _utc_now_naive()
    min_time = now - lookback
    max_time = now + timedelta(minutes=10)

    points: list[CsvPoint] = []
    timestamp_columns = _detect_timestamp_columns(fieldnames)
    basename_columns = _detect_basename_columns(fieldnames)

    stats = {
        "rows_scanned": 0,
        "dropped_no_y": 0,
        "dropped_no_x": 0,
        "dropped_outside_window": 0,
    }

    for row_number, row in iter_csv_rows(csv_path, fieldnames, has_header):
        stats["rows_scanned"] += 1

        y_value = _parse_float(row.get(y_column, ""))
        if y_value is None:
            stats["dropped_no_y"] += 1
            continue

        basename = _pick_basename(row, basename_columns)

        if x_mode == X_MODE_BASENAME_TIME:
            x_time = extract_timestamp_from_basename(basename)
        else:
            x_time = _pick_timestamp(row, timestamp_columns)
            if x_time is None:
                # Fallback to basename time for rows missing explicit execution time.
                x_time = extract_timestamp_from_basename(basename)

        if x_time is None:
            stats["dropped_no_x"] += 1
            continue

        if x_time < min_time or x_time > max_time:
            stats["dropped_outside_window"] += 1
            continue

        points.append(
            CsvPoint(
                x_time=x_time,
                y_value=y_value,
                row_number=row_number,
                basename=basename,
            )
        )

    points.sort(key=lambda item: item.x_time)
    return points, stats


def load_app_config(config_path: Path) -> dict:
    merged = dict(DEFAULT_CONFIG)
    if not config_path.exists():
        return merged

    try:
        loaded = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return merged

    if not isinstance(loaded, dict):
        return merged

    for key, default_value in DEFAULT_CONFIG.items():
        value = loaded.get(key, default_value)
        if key == "recent_csv_paths":
            if isinstance(value, list):
                merged[key] = [str(item) for item in value if str(item).strip()]
            else:
                merged[key] = []
        else:
            merged[key] = value

    if merged.get("startup_x_mode") not in X_MODE_CHOICES:
        merged["startup_x_mode"] = X_MODE_RECORD_TIME

    return merged


def save_app_config(config_path: Path, config_data: dict) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(DEFAULT_CONFIG)
    payload.update(config_data)
    payload["recent_csv_paths"] = _dedupe_keep_order(
        [str(item) for item in payload.get("recent_csv_paths", [])]
    )[:40]
    config_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class CsvColumnTimelineApp:
    def __init__(self, root, tk_module, ttk_module, filedialog_module, args: argparse.Namespace) -> None:
        self.root = root
        self.tk = tk_module
        self.ttk = ttk_module
        self.filedialog = filedialog_module

        self.repo_root = args.repo_root.resolve()
        self.config_path = args.config_path.resolve()
        self.config_data = load_app_config(self.config_path)

        self.max_rows = args.max_rows
        self.after_id: Optional[str] = None

        self.selected_csv_path: Optional[Path] = None
        self.fieldnames: list[str] = []
        self.has_header = True
        self.points: list[CsvPoint] = []

        startup_csv = args.csv_path
        if startup_csv is None and self.config_data.get("startup_csv_path"):
            startup_csv = Path(str(self.config_data.get("startup_csv_path")))

        startup_y = args.y_column or str(self.config_data.get("startup_y_column", ""))
        startup_mode = args.x_axis_mode
        if startup_mode is None:
            startup_mode = str(self.config_data.get("startup_x_mode", X_MODE_RECORD_TIME))
        if startup_mode not in X_MODE_CHOICES:
            startup_mode = X_MODE_RECORD_TIME

        lookback_default = (
            args.lookback_hours
            if args.lookback_hours is not None
            else float(self.config_data.get("startup_lookback_hours", 24.0))
        )
        refresh_default = (
            args.refresh_seconds
            if args.refresh_seconds is not None
            else int(self.config_data.get("startup_refresh_seconds", 30))
        )

        self.csv_var = self.tk.StringVar(value=str(startup_csv) if startup_csv else "")
        self.y_column_var = self.tk.StringVar(value=startup_y)
        self.x_mode_var = self.tk.StringVar(value=startup_mode)
        self.lookback_var = self.tk.StringVar(value=str(lookback_default))
        self.refresh_var = self.tk.StringVar(value=str(refresh_default))
        self.auto_refresh_var = self.tk.BooleanVar(value=True)
        self.status_var = self.tk.StringVar(value="Select CSV and click Open CSV.")

        self.csv_options = self._build_initial_csv_options()

        self._build_ui()

        if self.csv_var.get().strip():
            self._open_selected_csv(refresh_after_open=False)
            self._refresh_now()

    def _build_initial_csv_options(self) -> list[str]:
        candidates: list[str] = []

        startup = str(self.config_data.get("startup_csv_path", "")).strip()
        if startup:
            candidates.append(startup)

        candidates.extend(str(item) for item in self.config_data.get("recent_csv_paths", []))

        default_csv = self.repo_root / DEFAULT_CSV_REL
        if default_csv.exists():
            candidates.append(str(default_csv.resolve()))

        return _dedupe_keep_order(candidates)

    def _set_csv_options(self, values: list[str]) -> None:
        self.csv_options = _dedupe_keep_order(values)
        self.csv_combo["values"] = self.csv_options

    def _remember_recent_csv(self, csv_path: Path) -> None:
        absolute = str(csv_path.resolve())
        updated = [absolute]
        updated.extend(str(item) for item in self.config_data.get("recent_csv_paths", []))
        updated = _dedupe_keep_order(updated)[:40]

        self.config_data["recent_csv_paths"] = updated
        self._set_csv_options([absolute] + self.csv_options)
        try:
            save_app_config(self.config_path, self.config_data)
        except OSError:
            pass

    def _build_ui(self) -> None:
        self.root.title("CSV Column Timeline")
        self.root.geometry("1380x820")

        controls_top = self.ttk.Frame(self.root, padding=8)
        controls_top.pack(fill="x")

        self.ttk.Label(controls_top, text="CSV file").pack(side="left")
        self.csv_combo = self.ttk.Combobox(
            controls_top,
            width=86,
            textvariable=self.csv_var,
            values=self.csv_options,
        )
        self.csv_combo.pack(side="left", padx=(4, 8), fill="x", expand=True)

        self.ttk.Button(
            controls_top,
            text="Browse...",
            command=self._browse_csv,
        ).pack(side="left", padx=(0, 6))

        self.ttk.Button(
            controls_top,
            text="Open CSV",
            command=self._open_selected_csv,
        ).pack(side="left")

        controls_bottom = self.ttk.Frame(self.root, padding=(8, 0, 8, 8))
        controls_bottom.pack(fill="x")

        self.ttk.Label(controls_bottom, text="Y column").pack(side="left")
        self.y_combo = self.ttk.Combobox(
            controls_bottom,
            width=28,
            textvariable=self.y_column_var,
            values=[],
        )
        self.y_combo.pack(side="left", padx=(4, 12))

        self.ttk.Label(controls_bottom, text="X axis").pack(side="left")
        self.x_combo = self.ttk.Combobox(
            controls_bottom,
            width=18,
            textvariable=self.x_mode_var,
            values=list(X_MODE_CHOICES),
            state="readonly",
        )
        self.x_combo.pack(side="left", padx=(4, 12))

        self.ttk.Label(controls_bottom, text="Lookback (hours)").pack(side="left")
        self.ttk.Entry(controls_bottom, width=8, textvariable=self.lookback_var).pack(
            side="left", padx=(4, 12)
        )

        self.ttk.Label(controls_bottom, text="Refresh (s)").pack(side="left")
        self.ttk.Entry(controls_bottom, width=7, textvariable=self.refresh_var).pack(
            side="left", padx=(4, 12)
        )

        self.ttk.Checkbutton(
            controls_bottom,
            text="Auto Refresh",
            variable=self.auto_refresh_var,
        ).pack(side="left", padx=(0, 12))

        self.ttk.Button(
            controls_bottom,
            text="Refresh Now",
            command=self._refresh_now,
        ).pack(side="left", padx=(0, 8))

        self.ttk.Button(
            controls_bottom,
            text="Save To Open On Startup",
            command=self._save_startup_target,
        ).pack(side="left")

        self.canvas = self.tk.Canvas(self.root, bg="white", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.canvas.bind("<Configure>", lambda _event: self._draw_timeline())

        table_frame = self.ttk.Frame(self.root, padding=(8, 0, 8, 8))
        table_frame.pack(fill="both", expand=False)

        columns = ("x_time", "y_value", "basename", "row_number")
        self.table = self.ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            height=10,
        )
        self.table.heading("x_time", text="X time")
        self.table.heading("y_value", text="Y value")
        self.table.heading("basename", text="Basename")
        self.table.heading("row_number", text="CSV row")
        self.table.column("x_time", width=210, anchor="w")
        self.table.column("y_value", width=150, anchor="center")
        self.table.column("basename", width=360, anchor="w")
        self.table.column("row_number", width=90, anchor="center")

        scrollbar = self.ttk.Scrollbar(
            table_frame,
            orient="vertical",
            command=self.table.yview,
        )
        self.table.configure(yscrollcommand=scrollbar.set)
        self.table.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="left", fill="y")

        self.status_bar = self.ttk.Label(
            self.root,
            textvariable=self.status_var,
            anchor="w",
            padding=(8, 0, 8, 8),
        )
        self.status_bar.pack(fill="x")

    def _resolve_csv_path(self) -> Optional[Path]:
        text = self.csv_var.get().strip()
        if not text:
            return None

        path = Path(text).expanduser()
        if not path.is_absolute():
            path = self.repo_root / path

        try:
            return path.resolve()
        except OSError:
            return None

    def _browse_csv(self) -> None:
        selected = self.filedialog.askopenfilename(
            title="Select CSV file",
            initialdir=str(self.repo_root),
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not selected:
            return

        self.csv_var.set(selected)
        self._open_selected_csv()

    def _open_selected_csv(self, refresh_after_open: bool = True) -> None:
        csv_path = self._resolve_csv_path()
        if csv_path is None:
            self.status_var.set("Select a valid CSV path first.")
            return
        if not csv_path.exists():
            self.status_var.set(f"CSV not found: {csv_path}")
            return

        fieldnames, has_header = prepare_csv_layout(csv_path)
        if not fieldnames:
            self.status_var.set("Could not read CSV columns (empty or invalid CSV).")
            return

        self.selected_csv_path = csv_path
        self.fieldnames = fieldnames
        self.has_header = has_header

        numeric_columns = detect_numeric_columns(csv_path, self.fieldnames, self.has_header)
        self.y_combo["values"] = self.fieldnames

        current_y = self.y_column_var.get().strip()
        if current_y not in self.fieldnames:
            default_y = _default_y_column(self.fieldnames, numeric_columns)
            self.y_column_var.set(default_y or "")

        self.csv_var.set(str(csv_path))
        self._remember_recent_csv(csv_path)

        self.status_var.set(
            f"Opened {csv_path.name} | columns={len(self.fieldnames)} "
            f"| numeric_candidates={len(numeric_columns)}"
        )

        if refresh_after_open:
            self._refresh_now()

    def _read_runtime_config(self) -> tuple[Optional[dict], Optional[str]]:
        if self.selected_csv_path is None:
            return None, "No CSV opened."

        y_column = self.y_column_var.get().strip()
        if not y_column:
            return None, "Choose a Y column."
        if y_column not in self.fieldnames:
            return None, f"Y column not found in CSV: {y_column}"

        x_mode = self.x_mode_var.get().strip()
        if x_mode not in X_MODE_CHOICES:
            return None, f"Invalid X axis mode: {x_mode}"

        try:
            lookback_hours = float(self.lookback_var.get())
            refresh_seconds = int(self.refresh_var.get())
        except ValueError:
            return None, "Lookback and refresh must be numeric."

        if lookback_hours <= 0:
            return None, "Lookback must be > 0 hours."
        if refresh_seconds <= 0:
            return None, "Refresh must be > 0 seconds."

        return {
            "y_column": y_column,
            "x_mode": x_mode,
            "lookback_hours": lookback_hours,
            "refresh_seconds": refresh_seconds,
        }, None

    def _schedule_next(self, refresh_seconds: int) -> None:
        if not self.auto_refresh_var.get():
            return
        self.after_id = self.root.after(refresh_seconds * 1000, self._refresh_now)

    def _refresh_now(self) -> None:
        if self.after_id is not None:
            self.root.after_cancel(self.after_id)
            self.after_id = None

        runtime, error = self._read_runtime_config()
        if error is not None:
            self.status_var.set(f"Configuration error: {error}")
            self._draw_timeline()
            self._fill_table()
            self._schedule_next(5)
            return

        assert runtime is not None
        now_utc = _utc_now_naive()
        lookback = timedelta(hours=float(runtime["lookback_hours"]))

        points, stats = collect_series_points(
            self.selected_csv_path,
            fieldnames=self.fieldnames,
            has_header=self.has_header,
            y_column=str(runtime["y_column"]),
            x_mode=str(runtime["x_mode"]),
            lookback=lookback,
            now_utc=now_utc,
        )

        self.points = points
        self._draw_timeline()
        self._fill_table()

        latest_text = self.points[-1].x_time.strftime("%Y-%m-%d %H:%M:%S") if self.points else "-"
        mode_label = X_MODE_LABELS.get(str(runtime["x_mode"]), str(runtime["x_mode"]))
        self.status_var.set(
            f"Points: {len(self.points)} | Latest X: {latest_text} | "
            f"Rows scanned: {stats['rows_scanned']} | "
            f"drop(y/x/window)={stats['dropped_no_y']}/{stats['dropped_no_x']}/{stats['dropped_outside_window']} | "
            f"X mode: {mode_label}"
        )

        self._schedule_next(int(runtime["refresh_seconds"]))

    def _draw_timeline(self) -> None:
        self.canvas.delete("all")
        width = max(self.canvas.winfo_width(), 640)
        height = max(self.canvas.winfo_height(), 260)

        runtime, error = self._read_runtime_config()
        if error is not None or runtime is None:
            self.canvas.create_text(
                width // 2,
                height // 2,
                text="Open a CSV and choose a valid Y column to draw points.",
                fill="#444444",
                font=("TkDefaultFont", 12, "bold"),
            )
            return

        if not self.points:
            self.canvas.create_text(
                width // 2,
                height // 2,
                text="No points in selected lookback window.",
                fill="#444444",
                font=("TkDefaultFont", 12, "bold"),
            )
            return

        now_utc = _utc_now_naive()
        start_time = now_utc - timedelta(hours=float(runtime["lookback_hours"]))
        end_time = now_utc

        left = 88
        right = width - 20
        top = 24
        bottom = height - 40

        y_values = [point.y_value for point in self.points]
        y_min = min(y_values)
        y_max = max(y_values)
        if abs(y_max - y_min) < 1e-12:
            pad = max(abs(y_max), 1.0) * 0.05
            y_min -= pad
            y_max += pad

        x_span = max((end_time - start_time).total_seconds(), 1.0)
        y_span = max(y_max - y_min, 1e-12)

        def x_for_time(moment: datetime) -> float:
            elapsed = (moment - start_time).total_seconds()
            return left + (right - left) * (elapsed / x_span)

        def y_for_value(value: float) -> float:
            frac = (value - y_min) / y_span
            return bottom - (bottom - top) * frac

        # Grid and tick labels
        for tick in range(6):
            fraction = tick / 5
            x_pos = left + (right - left) * fraction
            tick_time = start_time + (end_time - start_time) * fraction
            self.canvas.create_line(x_pos, top - 4, x_pos, bottom + 4, fill="#e5e5e5")
            self.canvas.create_text(
                x_pos,
                bottom + 16,
                text=tick_time.strftime("%H:%M:%S"),
                fill="#555555",
                font=("TkDefaultFont", 8),
            )

        for tick in range(5):
            fraction = tick / 4
            y_pos = bottom - (bottom - top) * fraction
            y_val = y_min + y_span * fraction
            self.canvas.create_line(left - 4, y_pos, right, y_pos, fill="#f0f0f0")
            self.canvas.create_text(
                left - 8,
                y_pos,
                text=f"{y_val:.4g}",
                anchor="e",
                fill="#555555",
                font=("TkDefaultFont", 8),
            )

        # Axes
        self.canvas.create_line(left, top - 4, left, bottom + 2, fill="#777777")
        self.canvas.create_line(left, bottom, right + 2, bottom, fill="#777777")

        # Polyline + points
        coords: list[float] = []
        for point in self.points:
            x_pos = x_for_time(point.x_time)
            y_pos = y_for_value(point.y_value)
            coords.extend([x_pos, y_pos])

        if len(coords) >= 4:
            self.canvas.create_line(*coords, fill="#8fb5ff", width=1)

        for point in self.points:
            x_pos = x_for_time(point.x_time)
            y_pos = y_for_value(point.y_value)
            radius = 3
            self.canvas.create_oval(
                x_pos - radius,
                y_pos - radius,
                x_pos + radius,
                y_pos + radius,
                fill="#1f77b4",
                outline="#1f3d66",
            )

        title = (
            f"Y: {runtime['y_column']} | X mode: "
            f"{X_MODE_LABELS.get(str(runtime['x_mode']), str(runtime['x_mode']))}"
        )
        self.canvas.create_text(
            left,
            top - 12,
            text=title,
            anchor="w",
            font=("TkDefaultFont", 9, "bold"),
            fill="#333333",
        )

    def _fill_table(self) -> None:
        for item in self.table.get_children():
            self.table.delete(item)

        ordered = sorted(self.points, key=lambda item: item.x_time, reverse=True)
        for point in ordered[: self.max_rows]:
            self.table.insert(
                "",
                "end",
                values=(
                    point.x_time.strftime("%Y-%m-%d %H:%M:%S"),
                    f"{point.y_value:.8g}",
                    point.basename,
                    point.row_number,
                ),
            )

    def _save_startup_target(self) -> None:
        runtime, error = self._read_runtime_config()
        if error is not None:
            self.status_var.set(f"Cannot save startup target: {error}")
            return

        assert runtime is not None
        assert self.selected_csv_path is not None

        self.config_data["startup_csv_path"] = str(self.selected_csv_path.resolve())
        self.config_data["startup_y_column"] = str(runtime["y_column"])
        self.config_data["startup_x_mode"] = str(runtime["x_mode"])
        self.config_data["startup_lookback_hours"] = float(runtime["lookback_hours"])
        self.config_data["startup_refresh_seconds"] = int(runtime["refresh_seconds"])

        recent = [str(self.selected_csv_path.resolve())]
        recent.extend(str(item) for item in self.config_data.get("recent_csv_paths", []))
        self.config_data["recent_csv_paths"] = _dedupe_keep_order(recent)[:40]

        try:
            save_app_config(self.config_path, self.config_data)
            self.status_var.set(f"Saved startup target to {self.config_path}")
        except OSError as exc:
            self.status_var.set(f"Failed to save startup target: {exc}")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generic CSV timeline GUI.")

    script_dir = Path(__file__).resolve().parent

    parser.add_argument(
        "--repo-root",
        type=Path,
        default=get_repo_root(),
        help="Repository root (default: auto-detected).",
    )
    parser.add_argument(
        "--config-path",
        type=Path,
        default=script_dir / DEFAULT_CONFIG_FILENAME,
        help="Path to startup config JSON.",
    )
    parser.add_argument(
        "--csv-path",
        type=Path,
        default=None,
        help="CSV path to open immediately.",
    )
    parser.add_argument(
        "--y-column",
        default="",
        help="Y column to select on startup.",
    )
    parser.add_argument(
        "--x-axis-mode",
        choices=X_MODE_CHOICES,
        default=None,
        help="X axis mode (record_time or basename_time).",
    )
    parser.add_argument(
        "--lookback-hours",
        type=float,
        default=None,
        help="Lookback window in hours (defaults to startup config or 24).",
    )
    parser.add_argument(
        "--refresh-seconds",
        type=int,
        default=None,
        help="Refresh interval in seconds (defaults to startup config or 30).",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=500,
        help="Maximum number of rows displayed in the table.",
    )
    parser.add_argument(
        "--snapshot",
        action="store_true",
        help="Print a terminal snapshot and exit (no GUI).",
    )

    return parser.parse_args(argv)


def _run_snapshot(args: argparse.Namespace) -> int:
    config_data = load_app_config(args.config_path.resolve())

    csv_path = args.csv_path
    if csv_path is None and config_data.get("startup_csv_path"):
        csv_path = Path(str(config_data.get("startup_csv_path")))
    if csv_path is None:
        csv_path = args.repo_root.resolve() / DEFAULT_CSV_REL

    if not csv_path.is_absolute():
        csv_path = (args.repo_root.resolve() / csv_path).resolve()
    else:
        csv_path = csv_path.resolve()

    if not csv_path.exists():
        print(f"CSV not found: {csv_path}", file=sys.stderr)
        return 1

    fieldnames, has_header = prepare_csv_layout(csv_path)
    if not fieldnames:
        print("Could not parse CSV columns.", file=sys.stderr)
        return 1

    numeric_columns = detect_numeric_columns(csv_path, fieldnames, has_header)

    y_column = args.y_column or str(config_data.get("startup_y_column", "")).strip()
    if not y_column:
        guessed = _default_y_column(fieldnames, numeric_columns)
        if guessed is None:
            print("No Y column available.", file=sys.stderr)
            return 1
        y_column = guessed

    if y_column not in fieldnames:
        print(f"Y column not found in CSV: {y_column}", file=sys.stderr)
        return 1

    x_mode = args.x_axis_mode or str(config_data.get("startup_x_mode", X_MODE_RECORD_TIME))
    if x_mode not in X_MODE_CHOICES:
        x_mode = X_MODE_RECORD_TIME

    lookback_hours = (
        args.lookback_hours
        if args.lookback_hours is not None
        else float(config_data.get("startup_lookback_hours", 24.0))
    )

    points, stats = collect_series_points(
        csv_path,
        fieldnames=fieldnames,
        has_header=has_header,
        y_column=y_column,
        x_mode=x_mode,
        lookback=timedelta(hours=lookback_hours),
        now_utc=_utc_now_naive(),
    )

    print(f"csv={csv_path}")
    print(f"columns={len(fieldnames)}")
    print(f"y_column={y_column}")
    print(f"x_mode={x_mode}")
    print(f"points={len(points)}")
    print(
        "rows_scanned={rows_scanned} dropped_no_y={dropped_no_y} "
        "dropped_no_x={dropped_no_x} dropped_outside_window={dropped_outside_window}".format(
            **stats
        )
    )

    for point in points[-20:]:
        print(
            f"{point.x_time:%Y-%m-%d %H:%M:%S}  "
            f"y={point.y_value:.8g}  basename={point.basename}  row={point.row_number}"
        )

    return 0


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv or sys.argv[1:])

    if args.snapshot:
        return _run_snapshot(args)

    if not os.environ.get("DISPLAY"):
        print(
            "DISPLAY is not set. For remote GUI usage, connect with X11 forwarding "
            "(for example: ssh -X ...).",
            file=sys.stderr,
        )
        return 1

    try:
        import tkinter as tk
        from tkinter import filedialog, ttk
    except Exception as exc:
        print(f"Tkinter is required for this GUI: {exc}", file=sys.stderr)
        return 1

    root = tk.Tk()
    app = CsvColumnTimelineApp(root, tk, ttk, filedialog, args)
    del app
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
