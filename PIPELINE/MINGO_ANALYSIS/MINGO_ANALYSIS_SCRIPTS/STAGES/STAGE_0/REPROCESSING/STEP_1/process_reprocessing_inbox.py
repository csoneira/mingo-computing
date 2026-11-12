#!/usr/bin/env python3
"""Attend Stage 0 HLD retrieval petitions from a small text inbox.

Supported petition lines (one per request):
  dates 2026-10-20 2026-10-29
  force-dates 2026-10-20 2026-10-29
  name mi0126293003302
  force-name mi0126293003302

Successful petitions are removed from PETITIONS.txt and appended to
ATTENDED.md. The latter records retrieval/queue admission, not later analysis.
"""

from __future__ import annotations

import argparse
import fcntl
import re
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path


_REPO_IMPORT_ROOT = Path(__file__).resolve().parents[7]
if str(_REPO_IMPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_IMPORT_ROOT))
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.path_config import get_repo_root
ROOT = get_repo_root()
SCRIPT = ROOT / "PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/STEP_1/bring_reprocessing_files.sh"


def acquisition_date(basename: str) -> date | None:
    match = re.fullmatch(r"mi0([0-4])(\d{2})(\d{3})\d{6}", basename)
    if not match:
        return None
    _station, year, day_of_year = match.groups()
    try:
        return date(2000 + int(year), 1, 1) + timedelta(days=int(day_of_year) - 1)
    except ValueError:
        return None


def parse_petition(line: str, station: int) -> tuple[str, list[str]]:
    parts = line.strip().split()
    if not parts:
        raise ValueError("empty petition")
    if parts[0] in {"dates", "force-dates"} and len(parts) == 3:
        start, end = (date.fromisoformat(value) for value in parts[1:])
        if end < start:
            raise ValueError("end date is before start date")
        return ("forced date range" if parts[0] == "force-dates" else "date range"), [str(start), str(end)]
    if parts[0] in {"name", "force-name"} and len(parts) == 2:
        basename = parts[1]
        expected = re.fullmatch(rf"mi0{station}\d{{11}}", basename)
        if not expected:
            raise ValueError(f"{basename!r} is not a MINGO0{station} basename")
        return ("force exact basename" if parts[0] == "force-name" else "exact basename"), [basename]
    raise ValueError("use: dates YYYY-MM-DD YYYY-MM-DD | force-dates YYYY-MM-DD YYYY-MM-DD | name BASENAME | force-name BASENAME")


def run_request(station: int, petition: str, kind: str, args: list[str]) -> tuple[int, str, str]:
    command = ["bash", str(SCRIPT), str(station), "--refresh-metadata"]
    if "date range" in kind:
        command.extend([args[0][2:].replace("-", ""), args[1][2:].replace("-", "")])
        if kind.startswith("forced"):
            command.append("--force-reprocess")
    else:
        command.extend(["--basename", args[0]])
        if kind.startswith("force"):
            command.append("--force-reprocess")
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    output = (completed.stdout + completed.stderr).strip()
    if completed.returncode:
        return completed.returncode, output, "fetch failed; petition left in inbox"

    station_root = ROOT / f"PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO0{station}/STAGE_0/REPROCESSING"
    candidates: set[str] = set()
    if "date range" in kind:
        start, end = map(date.fromisoformat, args)
        metadata = station_root / "STEP_0/OUTPUT_FILES" / f"clean_remote_database_{station}.csv"
        if metadata.exists():
            for raw in metadata.read_text(errors="replace").splitlines()[1:]:
                name = raw.split(",", 1)[0].strip()
                acquired = acquisition_date(name)
                if acquired and start <= acquired <= end:
                    candidates.add(name)
    else:
        candidates.add(args[0])

    task3_metadata = (
        ROOT
        / f"PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO0{station}/STAGE_1/EVENT_DATA/STEP_1/TASK_3/METADATA/task_3_metadata_specific.csv"
    )
    completed_names: set[str] = set()
    if task3_metadata.is_file():
        with task3_metadata.open(encoding="utf-8", errors="replace") as handle:
            header = handle.readline().strip().split(",")
            if "filename_base" in header:
                name_index = header.index("filename_base")
                for row in handle:
                    fields = row.rstrip("\n").split(",")
                    if len(fields) > name_index:
                        completed_names.add(fields[name_index].strip().strip('"'))
    explicit_force = kind.startswith("force")
    already_analyzed = candidates & completed_names
    if not explicit_force:
        candidates.difference_update(completed_names)

    queue = station_root / "STEP_2/INPUT_FILES/UNPROCESSED"
    queue.mkdir(parents=True, exist_ok=True)
    compressed = station_root / "STEP_1/OUTPUT_FILES/COMPRESSED_HLDS"
    uncompressed = station_root / "STEP_1/OUTPUT_FILES/UNCOMPRESSED_HLDS"
    admitted: list[str] = []
    for name in sorted(candidates):
        if (queue / f"{name}.hld").exists():
            admitted.append(name)
            continue
        archive = compressed / f"{name}.hld.tar.gz"
        if archive.exists():
            result = subprocess.run(
                ["tar", "-xzf", str(archive), "--strip-components=3", "-C", str(queue)],
                text=True,
                capture_output=True,
            )
            if result.returncode:
                return result.returncode, output + "\n" + result.stderr, f"archive extraction failed for {name}; petition left in inbox"
            if (queue / f"{name}.hld").exists():
                archive.unlink()
                admitted.append(name)
        raw = uncompressed / f"{name}.hld"
        if raw.exists() and not (queue / raw.name).exists():
            raw.replace(queue / raw.name)
            admitted.append(name)

    locations = [
        queue,
        station_root / "STEP_2/INPUT_FILES/PROCESSING",
        station_root / "STEP_2/INPUT_FILES/COMPLETED",
    ]
    visible = set()
    for directory in locations:
        if directory.is_dir():
            visible.update(path.name.split(".hld", 1)[0] for path in directory.iterdir() if path.is_file())
    found = sorted(candidates & visible)
    interpretation = (
        f"{len(candidates) + len(already_analyzed)} remote metadata basename(s); "
        f"{len(already_analyzed)} already present in Task 3 metadata; "
        f"{len(admitted)} newly admitted to Stage 0 queue; {len(found)} present in Stage 0"
    )
    if "date range" in kind:
        interpretation += f" for {args[0]} through {args[1]}"
    else:
        interpretation += f" for {args[0]}"
    if not candidates and already_analyzed and not explicit_force:
        interpretation += "; duplicate-safe request skipped already analyzed files"
        status = "already satisfied"
    elif not found and candidates and any(
        phrase in output.lower()
        for phrase in ("already local/downstream", "no basenames remain to download")
    ):
        interpretation += "; request resolved as already fetched/completed, so duplicate fetch skipped"
        status = "already satisfied"
    elif found:
        status = "admitted to Stage 0 Step 2 UNPROCESSED queue"
    else:
        return 1, output, "no matching HLD was fetched or admitted; petition left in inbox"
    return 0, output, f"{interpretation}; {status}; basenames: {', '.join(found) if found else '(none observed)'}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("station", type=int, choices=range(1, 5))
    parser.add_argument("--once", action="store_true", help="attend at most one petition")
    opts = parser.parse_args()
    station = opts.station
    inbox = ROOT / f"PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO0{station}/STAGE_0/REPROCESSING/INBOX"
    inbox.mkdir(parents=True, exist_ok=True)
    petitions_file = inbox / "PETITIONS.txt"
    ledger = inbox / "ATTENDED.md"
    lock_path = inbox / ".processor.lock"
    petitions_file.touch(exist_ok=True)
    if not ledger.exists():
        ledger.write_text("# Attended Stage 0 petitions\n\nEach entry records retrieval and Stage 0 admission. It does not imply Task 3 analysis has completed.\n")

    with lock_path.open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Stage 0 petition inbox is already being processed; leaving it for the active worker.")
            return 0
        lines = petitions_file.read_text().splitlines()
        remaining: list[str] = []
        handled = 0
        for line_index, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                remaining.append(line)
                continue
            received = datetime.now().astimezone().isoformat(timespec="seconds")
            try:
                kind, parsed = parse_petition(stripped, station)
                code, output, interpretation = run_request(station, stripped, kind, parsed)
            except Exception as exc:  # retain malformed/unavailable petitions for correction/retry
                code, output, interpretation = 1, "", f"not attended: {type(exc).__name__}: {exc}"
                kind = "unparsed"
            if code:
                remaining.append(line)
                print(f"PENDING {stripped}: {interpretation}", file=sys.stderr)
            else:
                handled += 1
                with ledger.open("a") as history:
                    history.write(
                        f"\n## {received}\n\n"
                        f"- Petition: `{stripped}`\n"
                        f"- Interpreted as: {kind}\n"
                        f"- Outcome: {interpretation}\n"
                    )
                print(f"ATTENDED {stripped}: {interpretation}")
                if output:
                    print("\n".join(output.splitlines()[-8:]))
            if opts.once and handled:
                remaining.extend(lines[line_index + 1 :])
                break
        temp = petitions_file.with_suffix(".tmp")
        temp.write_text("\n".join(remaining) + ("\n" if remaining else ""))
        temp.replace(petitions_file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
