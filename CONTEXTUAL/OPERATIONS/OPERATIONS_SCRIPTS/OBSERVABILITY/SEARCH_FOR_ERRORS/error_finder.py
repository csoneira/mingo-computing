#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/OBSERVABILITY/SEARCH_FOR_ERRORS/error_finder.py
Purpose: Scan cron log files for Tracebacks and store the stack traces in a single report.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/OBSERVABILITY/SEARCH_FOR_ERRORS/error_finder.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from datetime import datetime, timezone
import re
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Set, Tuple

def resolve_project_root() -> Path:
    dataflow_root = os.environ.get("DATAFLOW_ROOT")
    if dataflow_root:
        candidate = Path(dataflow_root).expanduser()
        if (candidate / "CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME").is_dir():
            return candidate

    script_path = Path(__file__).resolve()
    for candidate in script_path.parents:
        if (candidate / "CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME").is_dir() and (candidate / "PIPELINE" / "MINGO_DIGITAL_TWIN").is_dir():
            return candidate

    parents = script_path.parents
    return parents[3] if len(parents) > 3 else script_path.parent


PROJECT_ROOT = resolve_project_root()
LOG_DIR = PROJECT_ROOT / "CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME" / "CRON_LOGS"
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "ERROR_SUMMARIES"
OUTPUT_FILE = OUTPUT_DIR / "cron_tracebacks.log"
STATE_FILE = OUTPUT_DIR / "error_finder_state.json"
TRACEBACK_CATALOG_FILE = OUTPUT_DIR / "traceback_catalog.json"
ISSUE_CATALOG_FILE = OUTPUT_DIR / "issue_catalog.json"
ISSUE_REPORT_FILE = OUTPUT_DIR / "cron_issue_typologies.log"

ENTRY_DIVIDER = "# --------------------"
MARKER_PREFIX = "### REVISED BY ERROR_FINDER AT "
TRACEBACK_TRIGGER = "Traceback (most recent call last):"
TIMESTAMP_PATTERNS = [
    re.compile(r"^\[?\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}"),
    re.compile(r"^[A-Z][a-z]{2} [A-Z][a-z]{2}\s+\d{1,2} \d{2}:\d{2}:\d{2}"),
]
ISSUE_TRIGGER_PATTERNS = [
    re.compile(r"\[(warn|warning|error|err|critical|fatal|panic)\]", re.IGNORECASE),
    re.compile(r"\bwarning\b", re.IGNORECASE),
    re.compile(r"\berror\b", re.IGNORECASE),
    re.compile(r"\bfailed\b", re.IGNORECASE),
    re.compile(
        r"\b(exception|fatal|panic|segmentation fault|permission denied|timed out?|"
        r"runtimeerror|valueerror|keyerror|filenotfounderror|oserror)\b",
        re.IGNORECASE,
    ),
]
ISSUE_EXCLUDE_PATTERNS = [
    re.compile(r"\bno errors found\b", re.IGNORECASE),
    re.compile(r"\bno new errors\b", re.IGNORECASE),
    re.compile(r"^-->\s+Cleaning\s+.*/(?:ERROR|ERROR_DIRECTORY)\b", re.IGNORECASE),
    re.compile(r"^Completed/Error directories cleaned:", re.IGNORECASE),
    re.compile(r"^\s*-\s+completed/error directories:", re.IGNORECASE),
]
PATH_PATTERN = re.compile(r"/[^\s'\"]+")
LEVEL_TOKEN_PATTERN = re.compile(
    r"\[(trace|debug|info|notice|warn|warning|error|err|critical|fatal|panic)\]",
    re.IGNORECASE,
)


def is_timestamp_line(line: str) -> bool:
    return any(pattern.match(line) for pattern in TIMESTAMP_PATTERNS)


def load_known_hashes(state_path: Path) -> Set[str]:
    if not state_path.exists():
        return set()
    try:
        with state_path.open("r", encoding="utf-8") as fp:
            data = json.load(fp)
    except json.JSONDecodeError:
        return set()
    hashes = data.get("known_hashes", [])
    return set(hashes)


def save_known_hashes(state_path: Path, hashes: Set[str]) -> None:
    state_path.write_text(
        json.dumps({"known_hashes": sorted(hashes)}, indent=2),
        encoding="utf-8",
    )


def load_traceback_catalog(catalog_path: Path) -> Dict[str, Dict[str, str]]:
    if not catalog_path.exists():
        return {}
    try:
        with catalog_path.open("r", encoding="utf-8") as fp:
            data = json.load(fp)
    except json.JSONDecodeError:
        return {}
    if isinstance(data, dict):
        return data
    return {}


def save_traceback_catalog(catalog_path: Path, catalog: Dict[str, Dict[str, str]]) -> None:
    catalog_path.write_text(
        json.dumps(catalog, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def load_issue_catalog(catalog_path: Path) -> Dict[str, Dict[str, object]]:
    if not catalog_path.exists():
        return {}
    try:
        with catalog_path.open("r", encoding="utf-8") as fp:
            data = json.load(fp)
    except json.JSONDecodeError:
        return {}
    if isinstance(data, dict):
        return data
    return {}


def save_issue_catalog(catalog_path: Path, catalog: Dict[str, Dict[str, object]]) -> None:
    catalog_path.write_text(
        json.dumps(catalog, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def read_lines_after_last_marker(log_path: Path, *, full_scan: bool = False) -> Tuple[List[str], bool]:
    try:
        raw_text = log_path.read_text(encoding="utf-8", errors="ignore")
    except FileNotFoundError:
        return [], False
    lines = raw_text.splitlines()
    if full_scan:
        return lines, False
    last_marker_index = -1
    for idx, line in enumerate(lines):
        if line.startswith(MARKER_PREFIX):
            last_marker_index = idx
    start_index = last_marker_index + 1
    if start_index >= len(lines):
        return [], False
    return lines[start_index:], True


def extract_traceback_ranges(lines: Sequence[str]) -> List[Tuple[int, int]]:
    ranges: List[Tuple[int, int]] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if TRACEBACK_TRIGGER in line:
            j = i + 1
            seen_exception_line = False
            while j < len(lines):
                current = lines[j]
                if current.startswith(MARKER_PREFIX):
                    break
                if TRACEBACK_TRIGGER in current:
                    break
                if is_timestamp_line(current):
                    break
                if not current.strip():
                    j += 1
                    break
                is_indented = current.startswith((" ", "\t"))
                if not is_indented and seen_exception_line:
                    break
                if not is_indented:
                    seen_exception_line = True
                j += 1
            ranges.append((i, j))
            i = j
        else:
            i += 1
    return ranges


def extract_tracebacks(lines: Sequence[str]) -> List[str]:
    tracebacks: List[str] = []
    for start, end in extract_traceback_ranges(lines):
        block = lines[start:end]
        tracebacks.append("\n".join(block).strip())
    return tracebacks


def should_keep_issue_line(line: str) -> bool:
    lowered = line.strip()
    if not lowered:
        return False
    if lowered.startswith(MARKER_PREFIX):
        return False
    for pattern in ISSUE_EXCLUDE_PATTERNS:
        if pattern.search(lowered):
            return False
    return any(pattern.search(lowered) for pattern in ISSUE_TRIGGER_PATTERNS)


def normalize_issue_signature(line: str) -> str:
    out = line.strip()
    out = re.sub(r"\b\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:Z| UTC)?\b", "<TS>", out)
    out = PATH_PATTERN.sub("<PATH>", out)
    out = re.sub(r"\b\d+\b", "<N>", out)
    out = re.sub(r"\s+", " ", out)
    return out


def classify_issue_severity(text: str) -> str:
    lowered = text.lower()

    # Prefer explicit structured log levels from the line itself.
    levels = [match.group(1).lower() for match in LEVEL_TOKEN_PATTERN.finditer(text)]
    if levels:
        if any(level in {"error", "err", "critical", "fatal", "panic"} for level in levels):
            return "ERROR"
        if any(level in {"warn", "warning"} for level in levels):
            return "WARN"

    if "warning" in lowered:
        return "WARN"
    if any(token in lowered for token in ("error", "failed", "exception", "fatal", "panic")):
        return "ERROR"
    return "WARN"


def extract_issue_lines(lines: Sequence[str]) -> List[str]:
    ranges = extract_traceback_ranges(lines)
    covered = [False] * len(lines)
    for start, end in ranges:
        for idx in range(start, min(end, len(lines))):
            covered[idx] = True

    issues: List[str] = []
    for idx, line in enumerate(lines):
        if covered[idx]:
            continue
        if should_keep_issue_line(line):
            issues.append(line.strip())
    return issues


def traceback_terminal_line(traceback_text: str) -> str:
    parts = [line.strip() for line in traceback_text.splitlines() if line.strip()]
    if not parts:
        return traceback_text.strip()
    for line in reversed(parts):
        if line == "^":
            continue
        if re.search(r"(error|exception|failed|fatal|panic)", line, re.IGNORECASE):
            return line
    for line in reversed(parts):
        if line != "^":
            return line
    return parts[-1]


def append_marker(log_path: Path, timestamp: str) -> None:
    try:
        with log_path.open("a", encoding="utf-8") as fp:
            fp.write(f"\n{MARKER_PREFIX}{timestamp} ###\n")
    except OSError:
        # Keep scanning resilient even if one log file cannot be written.
        return


def append_entries(entries: Iterable[Tuple[str, str, str, str]]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with OUTPUT_FILE.open("a", encoding="utf-8") as fp:
        for timestamp, log_name, digest, traceback_text in entries:
            fp.write(f"{ENTRY_DIVIDER}\n")
            fp.write(f"{timestamp} | {log_name} | HASH {digest}\n")
            fp.write(f"{traceback_text}\n\n")


def append_issue_entries(entries: Iterable[Tuple[str, str, str, str, str, str]]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with ISSUE_REPORT_FILE.open("a", encoding="utf-8") as fp:
        for timestamp, log_name, severity, digest, signature, sample in entries:
            fp.write(f"{ENTRY_DIVIDER}\n")
            fp.write(f"{timestamp} | {severity} | {log_name} | HASH {digest}\n")
            fp.write(f"SIGNATURE: {signature}\n")
            fp.write(f"SAMPLE: {sample}\n\n")


def append_no_error_entry(timestamp: str) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with OUTPUT_FILE.open("a", encoding="utf-8") as fp:
        fp.write(f"{ENTRY_DIVIDER}\n")
        fp.write(f"{timestamp} | NO ERRORS FOUND\n\n")


def append_pending_entry(timestamp: str, pending_counts: Counter) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    total_occurrences = sum(pending_counts.values())
    unique = len(pending_counts)
    with OUTPUT_FILE.open("a", encoding="utf-8") as fp:
        fp.write(f"{ENTRY_DIVIDER}\n")
        fp.write(
            f"{timestamp} | NO NEW ERRORS, BUT STILL THESE ERRORS PENDING: "
            f"{total_occurrences} occurrences across {unique} tracebacks\n"
        )
        for digest, count in pending_counts.most_common():
            fp.write(f"  - {digest}: {count} occurrences (see {TRACEBACK_CATALOG_FILE.name})\n")
        fp.write("\n")


def process_log(log_path: Path, *, full_scan: bool = False) -> Tuple[List[str], List[str], bool]:
    lines, has_new_section = read_lines_after_last_marker(log_path, full_scan=full_scan)
    if not lines:
        return [], [], has_new_section
    tracebacks = extract_tracebacks(lines)
    issue_lines = extract_issue_lines(lines)
    return tracebacks, issue_lines, has_new_section


def iter_log_files(log_dir: Path) -> List[Path]:
    """Return all .log files under CRON_LOGS (recursive), sorted for stability."""
    return sorted(path for path in log_dir.rglob("*.log") if path.is_file())


def format_log_label(log_path: Path, root: Path) -> str:
    """Use CRON_LOGS-relative path for unambiguous source identification."""
    try:
        return str(log_path.relative_to(root))
    except ValueError:
        return log_path.name


def update_issue_catalog(
    *,
    catalog: Dict[str, Dict[str, object]],
    now: str,
    log_label: str,
    severity: str,
    signature: str,
    sample: str,
    new_entries: List[Tuple[str, str, str, str, str, str]],
) -> bool:
    digest = hashlib.sha1(signature.encode("utf-8")).hexdigest()
    entry = catalog.get(digest)
    if entry is None:
        catalog[digest] = {
            "severity": severity,
            "signature": signature,
            "sample": sample,
            "first_seen": now,
            "last_seen": now,
            "first_source_log": log_label,
            "occurrences": 1,
            "source_counts": {log_label: 1},
        }
        new_entries.append((now, log_label, severity, digest, signature, sample))
        return True

    entry["last_seen"] = now
    entry["occurrences"] = int(entry.get("occurrences", 0)) + 1
    src_counts = entry.get("source_counts")
    if not isinstance(src_counts, dict):
        src_counts = {}
    src_counts[log_label] = int(src_counts.get(log_label, 0)) + 1
    entry["source_counts"] = src_counts
    if entry.get("severity") == "WARN" and severity == "ERROR":
        entry["severity"] = "ERROR"
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect Tracebacks from cron logs into a single summary file.",
    )
    parser.add_argument(
        "--full-scan",
        action="store_true",
        help="Re-scan the complete cron logs, ignoring previous markers and state.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if not LOG_DIR.exists():
        raise SystemExit(f"Cron log directory not found: {LOG_DIR}")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    known_hashes = set() if args.full_scan else load_known_hashes(STATE_FILE)
    catalog = load_traceback_catalog(TRACEBACK_CATALOG_FILE)
    issue_catalog = {} if args.full_scan else load_issue_catalog(ISSUE_CATALOG_FILE)
    catalog_modified = False
    issue_catalog_modified = False
    entries_to_write: List[Tuple[str, str, str, str]] = []
    issue_entries_to_write: List[Tuple[str, str, str, str, str, str]] = []
    pending_counts: Counter = Counter()
    encountered_hashes: Set[str] = set()
    state_modified = args.full_scan

    for log_path in iter_log_files(LOG_DIR):
        log_label = format_log_label(log_path, LOG_DIR)
        tracebacks, issue_lines, has_new_content = process_log(log_path, full_scan=args.full_scan)
        for tb in tracebacks:
            digest = hashlib.sha1(tb.encode("utf-8")).hexdigest()
            encountered_hashes.add(digest)
            existing_entry = catalog.get(digest)
            if existing_entry:
                if existing_entry.get("traceback") != tb:
                    existing_entry["traceback"] = tb
                    catalog_modified = True
            else:
                catalog[digest] = {
                    "traceback": tb,
                    "first_seen": now,
                    "source_log": log_label,
                }
                catalog_modified = True
            if digest in known_hashes:
                pending_counts[digest] += 1
                continue
            known_hashes.add(digest)
            state_modified = True
            entries_to_write.append((now, log_label, digest, tb))

            terminal = traceback_terminal_line(tb)
            signature = normalize_issue_signature(terminal)
            severity = classify_issue_severity(terminal)
            issue_catalog_modified |= update_issue_catalog(
                catalog=issue_catalog,
                now=now,
                log_label=log_label,
                severity=severity,
                signature=signature,
                sample=terminal,
                new_entries=issue_entries_to_write,
            )

        for issue_line in issue_lines:
            signature = normalize_issue_signature(issue_line)
            severity = classify_issue_severity(issue_line)
            issue_catalog_modified |= update_issue_catalog(
                catalog=issue_catalog,
                now=now,
                log_label=log_label,
                severity=severity,
                signature=signature,
                sample=issue_line,
                new_entries=issue_entries_to_write,
            )
        if has_new_content and not args.full_scan:
            append_marker(log_path, now)

    # Only treat hashes as resolved when performing a full scan. During the normal
    # incremental runs we only inspect the portion of the log written after our
    # previous marker, so the absence of a digest does not mean the error stopped
    # occurring. Deleting hashes in that situation caused the same traceback to be
    # reported repeatedly.
    if args.full_scan:
        resolved_hashes = {digest for digest in known_hashes if digest not in encountered_hashes}
        if resolved_hashes:
            known_hashes.difference_update(resolved_hashes)
            state_modified = True
            for digest in resolved_hashes:
                if digest in catalog:
                    del catalog[digest]
                    catalog_modified = True

    if entries_to_write:
        append_entries(entries_to_write)
    else:
        if pending_counts:
            append_pending_entry(now, pending_counts)
        else:
            append_no_error_entry(now)
    if state_modified:
        save_known_hashes(STATE_FILE, known_hashes)
    if catalog_modified:
        save_traceback_catalog(TRACEBACK_CATALOG_FILE, catalog)
    if issue_entries_to_write:
        append_issue_entries(issue_entries_to_write)
    if issue_catalog_modified:
        save_issue_catalog(ISSUE_CATALOG_FILE, issue_catalog)


if __name__ == "__main__":
    main()
