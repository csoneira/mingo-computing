
"""Shared parsing for station/date selection config with master overrides."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from pathlib import Path
import re
from typing import Iterable, Mapping, Optional, Sequence, Tuple

import yaml

from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.path_config import get_master_config_root


DateRange = Tuple[Optional[datetime], Optional[datetime]]
MASTER_SELECTION_FILENAME = "config_selection.yaml"


@dataclass(frozen=True)
class SelectionConfig:
    stations: Optional[Tuple[int, ...]]
    date_ranges: Tuple[DateRange, ...]
    station_date_ranges: Mapping[int, Tuple[DateRange, ...]]

    @property
    def has_date_filters(self) -> bool:
        return bool(self.date_ranges or self.station_date_ranges)


@dataclass(frozen=True)
class EventMarkerConfig:
    time: datetime
    label: str


def load_yaml_mapping(path: str | Path) -> Mapping[str, object]:
    file_path = Path(path).expanduser()
    if not file_path.exists():
        return {}
    try:
        with file_path.open("r", encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}
    except Exception:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _normalize_datetime_value(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _parse_date_value(value: object, *, is_end: bool = False) -> Optional[datetime]:
    if value in ("", None):
        return None
    if isinstance(value, datetime):
        return _normalize_datetime_value(value)
    if isinstance(value, date):
        return datetime.combine(value, time.max if is_end else time.min)

    text = str(value).strip()
    if not text:
        return None
    is_date_only = bool(
        re.fullmatch(r"\d{4}-\d{2}-\d{2}", text)
        or re.fullmatch(r"\d{4}/\d{2}/\d{2}", text)
        or re.fullmatch(r"\d{8}", text)
    )
    if text.endswith("Z") and "T" in text:
        text = text[:-1] + "+00:00"

    parsed: Optional[datetime] = None
    for fmt in (
        None,
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y/%m/%d",
        "%Y%m%d",
    ):
        try:
            if fmt is None:
                parsed = datetime.fromisoformat(text)
            else:
                parsed = datetime.strptime(text, fmt)
            break
        except Exception:
            parsed = None
    if parsed is None:
        return None
    parsed = _normalize_datetime_value(parsed)
    if is_date_only:
        return datetime.combine(parsed.date(), time.max if is_end else time.min)
    return parsed


def _normalize_station_list(value: object) -> Optional[Tuple[int, ...]]:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip().lower()
        if not text or text in {"all", "*"}:
            return None
        tokens = [tok for tok in re.split(r"[,;\s]+", text) if tok]
        parsed = []
        for token in tokens:
            station_id = parse_station_id(token)
            if station_id is None:
                continue
            parsed.append(station_id)
        if not parsed:
            return None
        return tuple(sorted(set(parsed)))
    if isinstance(value, (list, tuple, set)):
        parsed = []
        for item in value:
            if isinstance(item, str) and item.strip().lower() in {"all", "*"}:
                return None
            if isinstance(item, (int, float)):
                station_id = int(item)
            else:
                station_id = parse_station_id(item)
            if station_id is None:
                continue
            parsed.append(station_id)
        if not parsed:
            return None
        return tuple(sorted(set(parsed)))
    if isinstance(value, (int, float)):
        return (int(value),)
    return None


def _normalize_date_range(
    start_value: Optional[datetime],
    end_value: Optional[datetime],
) -> Optional[DateRange]:
    if start_value is None and end_value is None:
        return None
    if start_value is not None and end_value is not None and start_value > end_value:
        start_value, end_value = end_value, start_value
    return (start_value, end_value)


def _extract_range_stations(item: Mapping[str, object]) -> Optional[Tuple[int, ...]]:
    if "stations" in item:
        return _normalize_station_list(item.get("stations"))
    if "station" in item:
        return _normalize_station_list(item.get("station"))
    return None


def _append_range(
    range_value: Optional[DateRange],
    range_stations: Optional[Tuple[int, ...]],
    out_ranges: list[DateRange],
    out_station_ranges: dict[int, list[DateRange]],
) -> None:
    if range_value is None:
        return
    if range_stations is None:
        out_ranges.append(range_value)
        return
    for station_id in range_stations:
        out_station_ranges.setdefault(int(station_id), []).append(range_value)


def _extract_event_markers_from_mapping(
    raw_markers: object,
    *,
    station: int | str | None = None,
) -> list[EventMarkerConfig]:
    if not isinstance(raw_markers, list):
        return []

    station_id = parse_station_id(station) if station is not None else None
    markers: list[EventMarkerConfig] = []
    for index, item in enumerate(raw_markers, start=1):
        if not isinstance(item, Mapping):
            raise ValueError(
                f"event_markers entry #{index} must be a mapping with 'date' and 'label'."
            )

        raw_date = item.get("date")
        raw_label = item.get("label")
        if raw_date is None or raw_label is None:
            raise ValueError(
                f"event_markers entry #{index} must define both 'date' and 'label'."
            )

        marker_time = _parse_date_value(raw_date, is_end=False)
        if marker_time is None:
            raise ValueError(
                f"event_markers entry #{index} has an invalid date value: {raw_date!r}."
            )
        label = str(raw_label).strip()
        if not label:
            raise ValueError(f"event_markers entry #{index} has an empty label.")

        marker_stations = _extract_range_stations(item)
        if station_id is not None and marker_stations is not None and station_id not in marker_stations:
            continue
        markers.append(EventMarkerConfig(time=marker_time, label=label))
    return markers


def _collect_ranges_from_node(
    node: object,
    out_ranges: list[DateRange],
    out_station_ranges: dict[int, list[DateRange]],
) -> None:
    if not isinstance(node, Mapping):
        return

    selection_node = node.get("selection")
    if isinstance(selection_node, Mapping):
        range_list = selection_node.get("date_ranges")
        if isinstance(range_list, list):
            for item in range_list:
                if not isinstance(item, Mapping):
                    continue
                normalized = _normalize_date_range(
                    _parse_date_value(item.get("start"), is_end=False),
                    _parse_date_value(item.get("end"), is_end=True),
                )
                _append_range(
                    normalized,
                    _extract_range_stations(item),
                    out_ranges,
                    out_station_ranges,
                )

    legacy_range = node.get("date_range")
    if isinstance(legacy_range, Mapping):
        normalized = _normalize_date_range(
            _parse_date_value(legacy_range.get("start"), is_end=False),
            _parse_date_value(legacy_range.get("end"), is_end=True),
        )
        _append_range(
            normalized,
            _extract_range_stations(legacy_range),
            out_ranges,
            out_station_ranges,
        )

    legacy_ranges = node.get("date_ranges")
    if isinstance(legacy_ranges, list):
        for item in legacy_ranges:
            if not isinstance(item, Mapping):
                continue
            normalized = _normalize_date_range(
                _parse_date_value(item.get("start"), is_end=False),
                _parse_date_value(item.get("end"), is_end=True),
            )
            _append_range(
                normalized,
                _extract_range_stations(item),
                out_ranges,
                out_station_ranges,
            )


def _dedupe_ranges(ranges: Sequence[DateRange]) -> Tuple[DateRange, ...]:
    deduped_ranges: list[DateRange] = []
    seen_ranges: set[DateRange] = set()
    for item in ranges:
        if item in seen_ranges:
            continue
        seen_ranges.add(item)
        deduped_ranges.append(item)
    return tuple(deduped_ranges)


def _dedupe_station_ranges(
    station_ranges: Mapping[int, Sequence[DateRange]],
) -> dict[int, Tuple[DateRange, ...]]:
    return {
        int(station_id): _dedupe_ranges(ranges)
        for station_id, ranges in station_ranges.items()
        if ranges
    }


def extract_selection(config: Mapping[str, object]) -> SelectionConfig:
    ranges: list[DateRange] = []
    station_ranges: dict[int, list[DateRange]] = {}
    _collect_ranges_from_node(config, ranges, station_ranges)

    stations: Optional[Tuple[int, ...]] = None
    selection_node = config.get("selection")
    if isinstance(selection_node, Mapping):
        stations = _normalize_station_list(selection_node.get("stations"))
    if stations is None:
        stations = _normalize_station_list(config.get("stations"))

    return SelectionConfig(
        stations=stations,
        date_ranges=_dedupe_ranges(ranges),
        station_date_ranges=_dedupe_station_ranges(station_ranges),
    )


def extract_event_markers(
    config: Mapping[str, object],
    *,
    station: int | str | None = None,
) -> Tuple[EventMarkerConfig, ...]:
    markers: list[EventMarkerConfig] = []

    selection_node = config.get("selection")
    if isinstance(selection_node, Mapping):
        markers.extend(
            _extract_event_markers_from_mapping(
                selection_node.get("event_markers"),
                station=station,
            )
        )

    markers.extend(
        _extract_event_markers_from_mapping(
            config.get("event_markers"),
            station=station,
        )
    )

    deduped: list[EventMarkerConfig] = []
    seen: set[tuple[datetime, str]] = set()
    for marker in sorted(markers, key=lambda item: item.time):
        key = (marker.time, marker.label)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(marker)
    return tuple(deduped)


def combine_local_selections(configs: Sequence[Mapping[str, object]]) -> SelectionConfig:
    combined_ranges: list[DateRange] = []
    combined_station_ranges: dict[int, list[DateRange]] = {}
    stations: Optional[Tuple[int, ...]] = None
    for config in configs:
        selection = extract_selection(config)
        if selection.stations is not None:
            stations = selection.stations
        combined_ranges.extend(selection.date_ranges)
        for station_id, ranges in selection.station_date_ranges.items():
            combined_station_ranges.setdefault(int(station_id), []).extend(ranges)

    return SelectionConfig(
        stations=stations,
        date_ranges=_dedupe_ranges(combined_ranges),
        station_date_ranges=_dedupe_station_ranges(combined_station_ranges),
    )


def load_master_selection(master_config_root: str | Path | None = None) -> SelectionConfig:
    root = Path(master_config_root).expanduser() if master_config_root is not None else get_master_config_root()
    config = load_yaml_mapping(root / MASTER_SELECTION_FILENAME)
    return extract_selection(config)


def load_master_event_markers(
    *,
    station: int | str | None = None,
    master_config_root: str | Path | None = None,
) -> Tuple[EventMarkerConfig, ...]:
    root = Path(master_config_root).expanduser() if master_config_root is not None else get_master_config_root()
    config = load_yaml_mapping(root / MASTER_SELECTION_FILENAME)
    return extract_event_markers(config, station=station)


def resolve_selection_from_configs(
    configs: Sequence[Mapping[str, object]],
    *,
    master_config_root: str | Path | None = None,
) -> SelectionConfig:
    local_selection = combine_local_selections(configs)
    master_selection = load_master_selection(master_config_root)

    stations = (
        master_selection.stations
        if master_selection.stations is not None
        else local_selection.stations
    )
    date_selection = master_selection if master_selection.has_date_filters else local_selection
    return SelectionConfig(
        stations=stations,
        date_ranges=date_selection.date_ranges,
        station_date_ranges=date_selection.station_date_ranges,
    )


def load_selection_for_paths(
    config_paths: Iterable[str | Path],
    *,
    master_config_root: str | Path | None = None,
) -> SelectionConfig:
    configs = [load_yaml_mapping(path) for path in config_paths]
    return resolve_selection_from_configs(configs, master_config_root=master_config_root)


def station_is_selected(station: int | str, stations: Optional[Sequence[int]]) -> bool:
    station_id = parse_station_id(station)
    if station_id is None:
        return False
    if stations is None:
        return True
    return station_id in set(int(item) for item in stations)


def parse_station_id(station: int | str) -> Optional[int]:
    try:
        return int(str(station))
    except Exception:
        pass

    text = str(station).strip().lower()
    if not text:
        return None

    # Common tokens used across the pipeline:
    # - "MINGO00"
    # - "mi00", and even full basenames like "mi00YYDDDHHMMSS"
    if text.startswith("mingo"):
        tail = text[5:]
        digits = "".join(ch for ch in tail if ch.isdigit())
        if digits:
            try:
                return int(digits)
            except Exception:
                return None

    if text.startswith("mi") and len(text) >= 4 and text[2:4].isdigit():
        try:
            return int(text[2:4])
        except Exception:
            return None

    return None


def date_filter_allowed_for_station(station: int | str) -> bool:
    station_id = parse_station_id(station)
    if station_id is None:
        return True
    return station_id != 0


def effective_date_ranges_for_station(
    station: int | str,
    selection_or_ranges: SelectionConfig | Sequence[DateRange],
    station_date_ranges: Optional[Mapping[int, Sequence[DateRange]]] = None,
) -> Tuple[DateRange, ...]:
    if not date_filter_allowed_for_station(station):
        return ()

    common_ranges: Sequence[DateRange]
    station_specific_ranges: Mapping[int, Sequence[DateRange]]
    if isinstance(selection_or_ranges, SelectionConfig):
        common_ranges = selection_or_ranges.date_ranges
        station_specific_ranges = selection_or_ranges.station_date_ranges
    else:
        common_ranges = selection_or_ranges
        station_specific_ranges = station_date_ranges or {}

    resolved_ranges: list[DateRange] = list(common_ranges)
    station_id = parse_station_id(station)
    if station_id is not None:
        resolved_ranges.extend(station_specific_ranges.get(int(station_id), ()))
    return _dedupe_ranges(resolved_ranges)


def date_in_ranges(day_value: date, ranges: Sequence[DateRange]) -> bool:
    if not ranges:
        return True
    day_start = datetime.combine(day_value, time.min)
    day_end = datetime.combine(day_value, time.max)
    for start_value, end_value in ranges:
        if start_value is not None and day_end < start_value:
            continue
        if end_value is not None and day_start > end_value:
            continue
        return True
    return False


def datetime_in_ranges(value: datetime, ranges: Sequence[DateRange]) -> bool:
    if not ranges:
        return True
    normalized_value = _normalize_datetime_value(value)
    for start_value, end_value in ranges:
        if start_value is not None and normalized_value < start_value:
            continue
        if end_value is not None and normalized_value > end_value:
            continue
        return True
    return False


def format_datetime_bound_for_display(value: Optional[datetime], *, is_end: bool) -> str:
    if value is None:
        return ""
    normalized_value = _normalize_datetime_value(value)
    boundary_time = time.max if is_end else time.min
    if normalized_value.time() == boundary_time:
        return normalized_value.date().isoformat()
    timespec = "microseconds" if normalized_value.microsecond else "seconds"
    return normalized_value.isoformat(sep=" ", timespec=timespec)


def format_date_range_for_display(
    start_value: Optional[datetime],
    end_value: Optional[datetime],
) -> str:
    start_text = format_datetime_bound_for_display(start_value, is_end=False) or "-inf"
    end_text = format_datetime_bound_for_display(end_value, is_end=True) or "+inf"
    return f"{start_text} to {end_text}"


def serialize_date_ranges_for_shell(ranges: Sequence[DateRange]) -> tuple[str, str]:
    epoch_chunks: list[str] = []
    label_chunks: list[str] = []

    for start_value, end_value in ranges:
        start_epoch = ""
        end_epoch = ""
        if start_value is not None:
            start_epoch = str(int(start_value.replace(tzinfo=timezone.utc).timestamp()))
        if end_value is not None:
            end_epoch = str(int(end_value.replace(tzinfo=timezone.utc).timestamp()))
        epoch_chunks.append(f"{start_epoch},{end_epoch}")
        label_chunks.append(
            f"{format_datetime_bound_for_display(start_value, is_end=False)}|"
            f"{format_datetime_bound_for_display(end_value, is_end=True)}"
        )

    return ";".join(epoch_chunks), ";".join(label_chunks)
