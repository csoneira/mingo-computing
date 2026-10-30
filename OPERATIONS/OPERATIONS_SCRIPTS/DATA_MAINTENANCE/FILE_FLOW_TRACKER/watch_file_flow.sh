#!/usr/bin/env bash

set -euo pipefail

ROWS="${ROWS:-25}"
TIMELINE_MINUTES="${TIMELINE_MINUTES:-10}"
TIMELINE_FILES="${TIMELINE_FILES:-12}"
TIMELINE_COLUMNS="${TIMELINE_COLUMNS:-12}"
TEST_MODE=0
TEST_DIR=""
TEST_HISTORY_CSV=""

usage() {
    cat <<EOF_USAGE
Usage:
    $(basename "$0")                   Show all stations
    $(basename "$0") NUMBER            Show one station
    $(basename "$0") --test            Run with synthetic data
    $(basename "$0") --test NUMBER     Synthetic data, one station

Examples:
    $(basename "$0")
    $(basename "$0") 2
    $(basename "$0") --test

Environment variables:
    ROWS=40 $(basename "$0")
    TIMELINE_MINUTES=15 $(basename "$0")
    TIMELINE_FILES=20 $(basename "$0")
    TIMELINE_COLUMNS=12 $(basename "$0")
    FILE_FLOW_HISTORY_DIR=/tmp/my-flow-history $(basename "$0")
EOF_USAGE
}

if [[ "${1:-}" == "--test" ]]; then
    TEST_MODE=1
    shift
fi

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    usage
    exit 0
fi

if (( $# > 1 )); then
    printf '\033[31mERROR: too many arguments.\033[0m\n' >&2
    usage >&2
    exit 2
fi

if (( $# == 1 )) && [[ ! "$1" =~ ^[0-9]+$ ]]; then
    printf '\033[31mERROR: station must be given as a number.\033[0m\n' >&2
    usage >&2
    exit 2
fi

# Resolve the checkout from this script's location when production data is used
# and the caller did not provide DATAFLOW_ROOT.
if (( TEST_MODE == 0 )) && [[ -z "${DATAFLOW_ROOT:-}" ]]; then
    _repo_probe="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
    while [[ "$_repo_probe" != "/" && ! -f "$_repo_probe/CONFIG/CONTENTS/environment/dataflow.sh" ]]; do
        _repo_probe="$(dirname -- "$_repo_probe")"
    done
    if [[ -f "$_repo_probe/CONFIG/CONTENTS/environment/dataflow.sh" ]]; then
        # shellcheck source=/dev/null
        source "$_repo_probe/CONFIG/CONTENTS/environment/dataflow.sh"
    else
        echo "Could not locate repository root from ${BASH_SOURCE[0]}" >&2
        exit 2
    fi
    unset _repo_probe
fi

if (( TEST_MODE == 1 )); then
    TEST_DIR="$(mktemp -d)"
    trap 'rm -rf -- "$TEST_DIR"' EXIT
    TRACKER_DIR="$TEST_DIR"
    TEST_HISTORY_CSV="$TEST_DIR/sample_timeline_history.csv"

    # Create a false but schema-compatible current table plus a multi-snapshot
    # history table. This exercises the same reader and timeline renderer used
    # for production data without touching OPERATIONS_RUNTIME.
    python3 - "$TEST_DIR" <<'PY_TEST_DATA'
import csv
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

root = Path(sys.argv[1])
now = datetime.now(timezone.utc).replace(second=0, microsecond=0)

fields = [
    "observed_at_utc", "station", "filename_base", "event_time_utc",
    "in_selected_range", "lifecycle_state", "highest_task_reached",
    "archive_present", "archive_valid", "metadata_tasks",
    "metadata_file_count", "newest_metadata_timestamp_utc",
    "stage0_present", "active_reprocessing",
    "task_0_state", "task_1_state", "task_2_state", "task_3_state",
    "task_4_state", "task_5_state", "pipeline_consistent",
    "needs_reprocessing", "anomaly_codes", "recommended_action",
    "artifact_count", "newest_artifact_mtime_utc", "current_paths",
]


def ts(minutes_ago):
    return (now - timedelta(minutes=minutes_ago)).isoformat()


def make_row(station, name, minutes_ago, highest, *, active=None, archive=False,
             lifecycle="stage1", anomaly=""):
    row = {field: "" for field in fields}
    row.update({
        "observed_at_utc": ts(minutes_ago),
        "station": f"MINGO{station:02d}",
        "filename_base": name,
        "event_time_utc": ts(30 + minutes_ago),
        "in_selected_range": "true",
        "lifecycle_state": "archived" if archive else lifecycle,
        "highest_task_reached": str(highest) if highest is not None else "",
        "archive_present": "true" if archive else "false",
        "archive_valid": "true" if archive else "false",
        "stage0_present": "true" if highest is None else "false",
        "active_reprocessing": "true" if active is not None else "false",
        "pipeline_consistent": "false" if anomaly else "true",
        "needs_reprocessing": "true" if anomaly else "false",
        "anomaly_codes": anomaly,
        "recommended_action": "review" if anomaly else "none",
        "artifact_count": "2",
        "newest_artifact_mtime_utc": ts(minutes_ago),
        "current_paths": f"/synthetic/{name}",
    })
    for task in range(6):
        if highest is not None and task <= highest:
            row[f"task_{task}_state"] = "completed"
        else:
            row[f"task_{task}_state"] = "not_reached"
    if active is not None:
        row[f"task_{active}_state"] = "processing"
    return row

# Several files move at different rates. File A progresses continuously, file B
# starts later, file C starts later still, and file D enters an error.
snapshots = [
    make_row(2, "mi022630300001", 8, 0),
    make_row(2, "mi022630300001", 6, 1),
    make_row(2, "mi022630300101", 6, 0),
    make_row(2, "mi022630300001", 4, 2),
    make_row(2, "mi022630300101", 4, 1),
    make_row(3, "mi032630300201", 4, 0),
    make_row(2, "mi022630300001", 2, 3),
    make_row(2, "mi022630300101", 2, 2),
    make_row(3, "mi032630300201", 2, 1),
    make_row(3, "mi032630300301", 2, 0),
    make_row(2, "mi022630300001", 0, 4, active=5),
    make_row(2, "mi022630300101", 0, 3),
    make_row(3, "mi032630300201", 0, 2),
    make_row(3, "mi032630300301", 0, 0, lifecycle="manual_review", anomaly="synthetic_error"),
]

with (root / "sample_timeline_history.csv").open("w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=fields)
    writer.writeheader()
    writer.writerows(snapshots)

latest_by_key = {}
for row in snapshots:
    key = (row["station"], row["filename_base"])
    if key not in latest_by_key or row["observed_at_utc"] > latest_by_key[key]["observed_at_utc"]:
        latest_by_key[key] = row

for station in ("MINGO02", "MINGO03"):
    rows = [row for (st, _), row in latest_by_key.items() if st == station]
    with (root / f"{station}_file_flow_realtime.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
PY_TEST_DATA
else
    TRACKER_DIR="${DATAFLOW_ROOT}/OPERATIONS/OPERATIONS_RUNTIME/FILE_FLOW_TRACKER"
fi

CSV_FILES=()
DISPLAY_SCOPE="ALL STATIONS"

if (( $# == 0 )); then
    shopt -s nullglob
    CSV_FILES=("$TRACKER_DIR"/MINGO*_file_flow_realtime.csv)
    shopt -u nullglob
    if (( ${#CSV_FILES[@]} == 0 )); then
        printf '\033[31mERROR: no station CSV files found in %s\033[0m\n' "$TRACKER_DIR"
        exit 1
    fi
else
    STATION_NUMBER=$((10#$1))
    printf -v STATION_ID 'MINGO%02d' "$STATION_NUMBER"
    CSV="$TRACKER_DIR/${STATION_ID}_file_flow_realtime.csv"
    if [[ ! -r "$CSV" ]]; then
        printf '\033[31mERROR: cannot read %s\033[0m\n' "$CSV"
        exit 1
    fi
    CSV_FILES=("$CSV")
    DISPLAY_SCOPE="$STATION_ID"
fi

if (( TEST_MODE == 1 )); then
    DISPLAY_SCOPE="TEST DATA — ${DISPLAY_SCOPE}"
    HISTORY_FILE="$TEST_DIR/history_state.json"
else
    HISTORY_ROOT="${FILE_FLOW_HISTORY_DIR:-${XDG_RUNTIME_DIR:-/tmp}/mingo-file-flow-history-${UID}}"
    mkdir -p -- "$HISTORY_ROOT"
    if [[ "$DISPLAY_SCOPE" == "ALL STATIONS" ]]; then
        HISTORY_FILE="$HISTORY_ROOT/all_stations.json"
    else
        HISTORY_FILE="$HISTORY_ROOT/${DISPLAY_SCOPE}.json"
    fi
fi

python3 - \
    "$ROWS" \
    "$DISPLAY_SCOPE" \
    "$TIMELINE_MINUTES" \
    "$TIMELINE_FILES" \
    "$TIMELINE_COLUMNS" \
    "$HISTORY_FILE" \
    "$TEST_MODE" \
    "$TEST_HISTORY_CSV" \
    "${CSV_FILES[@]}" <<'PY'
import csv
import fcntl
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

max_rows = int(sys.argv[1])
display_scope = sys.argv[2]
timeline_minutes = max(1, int(sys.argv[3]))
timeline_files = max(1, int(sys.argv[4]))
timeline_columns = max(2, int(sys.argv[5]))
history_path = Path(sys.argv[6])
test_mode = sys.argv[7] == "1"
test_history_csv = Path(sys.argv[8]) if sys.argv[8] else None
csv_paths = [Path(path) for path in sys.argv[9:]]

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"


def true_value(value):
    return str(value).strip().lower() in {"1", "true", "yes"}


def shorten(value, width):
    value = str(value or "")
    return value if len(value) <= width else value[: width - 1] + "…"


def parse_datetime(value):
    value = str(value or "").strip()
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, AttributeError, OverflowError):
        return None


def parse_time(value):
    parsed = parse_datetime(value)
    return parsed.timestamp() if parsed else float("-inf")


def display_time(value):
    parsed = parse_datetime(value)
    return parsed.strftime("%Y-%m-%d %H:%M:%S") if parsed else (str(value or "-") or "-")


def task_symbol(value):
    state = str(value or "").strip().lower()
    if not state or state in {"not_reached", "none", "n/a"}:
        return f"{DIM}·{RESET}"
    if any(marker in state for marker in ("fail", "error", "invalid", "corrupt", "manual_review", "blocked")):
        return f"{RED}!{RESET}"
    if any(marker in state for marker in ("running", "processing", "active", "in_progress")):
        return f"{CYAN}▶{RESET}"
    if any(marker in state for marker in ("complete", "completed", "done", "success", "present", "current", "up_to_date", "archived", "valid")):
        return f"{GREEN}✓{RESET}"
    if any(marker in state for marker in ("out_of_date", "pending", "queued", "waiting", "reprocess")):
        return f"{YELLOW}○{RESET}"
    if state in {"missing", "absent", "false", "0"}:
        return f"{DIM}−{RESET}"
    return f"{MAGENTA}?{RESET}"


def row_priority(row):
    return (
        parse_time(row.get("newest_artifact_mtime_utc", "")),
        true_value(row.get("active_reprocessing", "")),
        true_value(row.get("in_selected_range", "")),
        true_value(row.get("needs_reprocessing", "")),
        bool(row.get("anomaly_codes", "").strip()),
        not true_value(row.get("pipeline_consistent", "")),
        parse_time(row.get("event_time_utc", "")),
    )


def stage_info(row):
    """Return a compact timeline token and an ordered progression rank."""
    lifecycle = str(row.get("lifecycle_state", "")).lower()
    anomaly = str(row.get("anomaly_codes", "")).strip()
    if anomaly or "manual_review" in lifecycle or "error" in lifecycle:
        return "!", -1

    for task in range(6):
        state = str(row.get(f"task_{task}_state", "")).lower()
        if any(marker in state for marker in ("running", "processing", "active", "in_progress")):
            return f"▶{task}", 10 + task

    if true_value(row.get("archive_valid", "")):
        return "P", 20

    highest = str(row.get("highest_task_reached", "")).strip()
    match = re.search(r"\d+", highest)
    if match:
        task = min(5, max(0, int(match.group(0))))
        return f"T{task}", 10 + task

    if true_value(row.get("stage0_present", "")):
        return "S0", 0

    return "?", -1


def state_signature(row):
    token, rank = stage_info(row)
    return {
        "token": token,
        "rank": rank,
        "lifecycle_state": str(row.get("lifecycle_state", "")),
        "archive_valid": str(row.get("archive_valid", "")),
        "active_reprocessing": str(row.get("active_reprocessing", "")),
        "anomaly_codes": str(row.get("anomaly_codes", "")),
        **{f"task_{task}_state": str(row.get(f"task_{task}_state", "")) for task in range(6)},
    }


def event_from_row(row, previous=None):
    token, rank = stage_info(row)
    observed = str(row.get("observed_at_utc", ""))
    previous_rank = previous.get("rank") if previous else None
    return {
        "observed_at_utc": observed,
        "station": str(row.get("station", "")).strip() or "?",
        "filename_base": str(row.get("filename_base", "")).strip(),
        "token": token,
        "rank": rank,
        "advanced": bool(previous_rank is not None and rank > previous_rank),
    }


def read_rows(paths):
    result = []
    errors = []
    for path in paths:
        try:
            with path.open(newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    row["_source_csv"] = path.name
                    result.append(row)
        except (OSError, csv.Error) as exc:
            errors.append(f"{path}: {exc}")
    return result, errors


def build_test_events(path, cutoff, allowed_stations):
    if path is None:
        return []
    rows, _ = read_rows([path])
    rows.sort(key=lambda row: parse_time(row.get("observed_at_utc", "")))
    last = {}
    events = []
    for row in rows:
        observed_dt = parse_datetime(row.get("observed_at_utc", ""))
        if not observed_dt or observed_dt < cutoff:
            continue
        if row.get("station", "").strip() not in allowed_stations:
            continue
        key = f"{row.get('station', '')}|{row.get('filename_base', '')}"
        signature = state_signature(row)
        previous = last.get(key)
        if previous is None or previous["signature"] != signature:
            events.append(event_from_row(row, previous))
        last[key] = {"signature": signature, "rank": signature["rank"]}
    return events


def update_runtime_history(current_rows, cutoff):
    history_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = history_path.with_suffix(history_path.suffix + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock_handle:
        fcntl.flock(lock_handle, fcntl.LOCK_EX)
        try:
            with history_path.open(encoding="utf-8") as handle:
                state = json.load(handle)
        except (OSError, json.JSONDecodeError, TypeError):
            state = {"last_seen": {}, "events": [], "last_snapshot": ""}

        last_seen = state.get("last_seen", {})
        events = state.get("events", [])
        observed_values = [row.get("observed_at_utc", "") for row in current_rows if row.get("observed_at_utc", "")]
        snapshot = max(observed_values, key=parse_time) if observed_values else ""

        # watch(1) may call this script every second while the realtime tracker
        # refreshes once per minute. Only ingest a new tracker snapshot once.
        if snapshot and snapshot != state.get("last_snapshot", ""):
            new_last_seen = {}
            for row in current_rows:
                key = f"{row.get('station', '')}|{row.get('filename_base', '')}"
                signature = state_signature(row)
                previous = last_seen.get(key)
                if previous is None or previous.get("signature") != signature:
                    events.append(event_from_row(row, previous))
                new_last_seen[key] = {
                    "signature": signature,
                    "rank": signature["rank"],
                }
            last_seen = new_last_seen
            state["last_snapshot"] = snapshot

        pruned = []
        for event in events:
            observed_dt = parse_datetime(event.get("observed_at_utc", ""))
            if observed_dt and observed_dt >= cutoff:
                pruned.append(event)

        state["last_seen"] = last_seen
        state["events"] = pruned
        temp_path = history_path.with_suffix(history_path.suffix + f".{os.getpid()}.tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(state, handle, separators=(",", ":"))
        os.replace(temp_path, history_path)
        return pruned


rows, read_errors = read_rows(csv_paths)
for error in read_errors:
    print(f"{RED}WARNING: {error}{RESET}", file=sys.stderr)
if not rows:
    print(f"{YELLOW}No tracker records were found in the selected CSV files.{RESET}")
    raise SystemExit(0)

rows.sort(key=row_priority, reverse=True)
selected_station_names = {row.get("station", "").strip() for row in rows if row.get("station", "").strip()}
now = datetime.now(timezone.utc)
cutoff = now - timedelta(minutes=timeline_minutes)
if test_mode:
    timeline_events = build_test_events(test_history_csv, cutoff, selected_station_names)
else:
    timeline_events = update_runtime_history(rows, cutoff)

stations = sorted({row.get("station", "").strip() for row in rows if row.get("station", "").strip()})
observed_values = [row.get("observed_at_utc", "") for row in rows if row.get("observed_at_utc", "")]
observed = max(observed_values, key=parse_time) if observed_values else "unknown"
total = len(rows)
selected = sum(true_value(row.get("in_selected_range", "")) for row in rows)
consistent = sum(true_value(row.get("pipeline_consistent", "")) for row in rows)
reprocess = sum(true_value(row.get("needs_reprocessing", "")) for row in rows)
active = sum(true_value(row.get("active_reprocessing", "")) for row in rows)
anomalous = sum(bool(row.get("anomaly_codes", "").strip()) for row in rows)
lifecycle_counts = Counter(row.get("lifecycle_state", "").strip() or "(empty)" for row in rows)
action_counts = Counter(row.get("recommended_action", "").strip() or "(none)" for row in rows)
station_counts = Counter(row.get("station", "").strip() or "(unknown)" for row in rows)

print(f"{BOLD}{CYAN}FILE FLOW TRACKER — {display_scope}{RESET}")
print(f"{DIM}Current:  {now.strftime('%Y-%m-%d %H:%M:%S')} UTC\nSnapshot: {display_time(observed)} UTC{RESET}")
print(
    f"CSV files: {BOLD}{len(csv_paths)}{RESET}   "
    f"Stations: {BOLD}{len(stations)}{RESET}   "
    f"Files: {BOLD}{total}{RESET}   "
    f"In range: {BLUE}{selected}{RESET}   "
    f"Consistent: {GREEN}{consistent}{RESET}   "
    f"Reprocess: {YELLOW}{reprocess}{RESET}   "
    f"Active: {CYAN}{active}{RESET}   "
    f"Anomalies: {RED}{anomalous}{RESET}"
)
if len(stations) > 1:
    print(f"{BOLD}Stations: {RESET}" + "  ".join(f"{name}={count}" for name, count in station_counts.most_common()))
print(f"{BOLD}Lifecycle:{RESET} " + "  ".join(f"{name}={count}" for name, count in lifecycle_counts.most_common(5)))
print(f"{BOLD}Actions:  {RESET} " + "  ".join(f"{name}={count}" for name, count in action_counts.most_common(4)))
print()

print(
    f"{BOLD}{'STATION':<8} {'FILE':<20} {'LAST MODIFIED':<19} {'EVENT TIME':<19} "
    f"{'R':<1} {'LIFECYCLE':<25} {'HIGH':>4} {'TASK FLOW':<23} {'ACTION / ANOMALY'}{RESET}"
)
print("─" * 158)
for row in rows[:max_rows]:
    selected_mark = f"{BLUE}●{RESET}" if true_value(row.get("in_selected_range", "")) else f"{DIM}·{RESET}"
    flow = " ".join(f"{task}:{task_symbol(row.get(f'task_{task}_state'))}" for task in range(6))
    lifecycle = row.get("lifecycle_state", "")
    lifecycle_text = f"{shorten(lifecycle, 25):<25}"
    if "manual_review" in lifecycle.lower():
        lifecycle_display = f"{RED}{lifecycle_text}{RESET}"
    elif true_value(row.get("active_reprocessing", "")):
        lifecycle_display = f"{CYAN}{lifecycle_text}{RESET}"
    elif true_value(row.get("needs_reprocessing", "")):
        lifecycle_display = f"{YELLOW}{lifecycle_text}{RESET}"
    else:
        lifecycle_display = lifecycle_text

    action = row.get("recommended_action", "").strip()
    anomaly = row.get("anomaly_codes", "").strip()
    detail = f"{action}; {anomaly}" if action and anomaly else (anomaly or action)
    if anomaly:
        detail = f"{RED}{shorten(detail, 35)}{RESET}"
    else:
        detail = shorten(detail, 35)

    print(
        f"{shorten(row.get('station', '?'), 8):<8} "
        f"{shorten(row.get('filename_base', ''), 20):<20} "
        f"{shorten(display_time(row.get('newest_artifact_mtime_utc', '')), 19):<19} "
        f"{shorten(display_time(row.get('event_time_utc', '')), 19):<19} "
        f"{selected_mark} "
        f"{lifecycle_display} "
        f"{shorten(row.get('highest_task_reached', ''), 4):>4} "
        f"{flow:<68} "
        f"{detail}"
    )

print()
print(f"{DIM}Sorted by LAST MODIFIED, newest first.{RESET}")
print(
    f"{DIM}Legend: {GREEN}✓ complete{RESET}{DIM}, {CYAN}▶ active{RESET}{DIM}, "
    f"{YELLOW}○ pending/outdated{RESET}{DIM}, {RED}! error/review{RESET}{DIM}, "
    f"· not reached, {BLUE}● selected range{RESET}"
)

# ---------------------------------------------------------------------------
# Recent state-change timeline
# ---------------------------------------------------------------------------

print()
print(f"{BOLD}{CYAN}RECENT FILE FLOW — last {timeline_minutes} min{RESET}")

valid_events = [
    event for event in timeline_events
    if event.get("filename_base") and parse_datetime(event.get("observed_at_utc", ""))
]

if not valid_events:
    print(f"{DIM}No file state changes have been observed in this window yet.{RESET}")
else:
    all_times = sorted({event["observed_at_utc"] for event in valid_events}, key=parse_time)
    if len(all_times) > timeline_columns:
        all_times = all_times[-timeline_columns:]
    time_set = set(all_times)
    valid_events = [event for event in valid_events if event["observed_at_utc"] in time_set]

    by_file = defaultdict(list)
    for event in valid_events:
        by_file[(event.get("station", "?"), event["filename_base"])].append(event)
    for events in by_file.values():
        events.sort(key=lambda event: parse_time(event["observed_at_utc"]))

    selected_files = sorted(
        by_file,
        key=lambda key: parse_time(by_file[key][-1]["observed_at_utc"]),
        reverse=True,
    )[:timeline_files]

    slot_width = 8
    left_width = 30
    centers = [index * slot_width + slot_width // 2 for index in range(len(all_times))]
    time_index = {value: index for index, value in enumerate(all_times)}

    header = " " * left_width + "".join(
        parse_datetime(value).strftime("%H:%M").center(slot_width)
        for value in all_times
    )
    print(header.rstrip())

    advances = Counter(
        event["observed_at_utc"]
        for event in valid_events
        if event.get("advanced")
    )
    advance_line = "ADVANCES".ljust(left_width) + "".join(
        str(advances.get(value, 0)).center(slot_width)
        for value in all_times
    )
    print(f"{DIM}{advance_line.rstrip()}{RESET}")

    for station, filename in selected_files:
        events = by_file[(station, filename)]
        canvas = [" "] * (len(all_times) * slot_width)
        event_positions = []
        for event in events:
            idx = time_index[event["observed_at_utc"]]
            token = event.get("token", "?")[:3]
            center = centers[idx]
            start = max(0, center - len(token) // 2)
            for offset, char in enumerate(token):
                pos = start + offset
                if pos < len(canvas):
                    canvas[pos] = char
            event_positions.append((idx, start, start + len(token) - 1, event))

        # A line means that the two state changes belong to the same logical
        # file. The node labels show the task reached at each change.
        for (_, _, right_a, _), (_, left_b, _, _) in zip(event_positions, event_positions[1:]):
            for pos in range(right_a + 1, left_b):
                if canvas[pos] == " ":
                    canvas[pos] = "-"

        label = f"{shorten(station, 8):<8} {shorten(filename, 20):<20}"
        print(f"{label:<{left_width}}{''.join(canvas).rstrip()}")

    hidden = len(by_file) - len(selected_files)
    if hidden > 0:
        print(f"{DIM}… {hidden} additional files with state changes hidden; set TIMELINE_FILES to show more.{RESET}")

    print(
        f"{DIM}Timeline nodes: S0=Stage 0, T0…T5=highest completed task, "
        f"▶n=task n active, P=valid Parquet, !=error/review. "
        f"Lines join successive observed state changes of the same file.{RESET}"
    )
    if test_mode:
        print(f"{DIM}TEST MODE uses synthetic CSV data only; production runtime files are untouched.{RESET}"
PY
