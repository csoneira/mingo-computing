"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/common/status_dashboard.py
Purpose: Utilities for aggregating status CSV logs and serving them for dashboards.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/common/status_dashboard.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterable, List, Dict, Optional
from urllib.parse import urlparse, parse_qs

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_OUTPUT = REPO_ROOT / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_SCRIPTS" / "common" / "status_dashboard" / "status_timeseries.csv"


def _iter_status_files(root: Path) -> Iterable[Path]:
    for path in root.glob("**/*_status.csv"):
        if path.name == "status_timeseries.csv":
            continue
        yield path


def _extract_station(path: Path) -> Optional[str]:
    for part in path.parts:
        if part.startswith("MINGO0") and len(part) == 7:
            return part[-1]
    return None


def collect_status_rows(
    root: Path,
    *,
    script: Optional[str] = None,
    station: Optional[str] = None,
) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for csv_path in _iter_status_files(root):
        script_name = csv_path.stem.replace("_status", "")
        station_name = _extract_station(csv_path)
        with csv_path.open(newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                continue
            for entry in reader:
                timestamp = entry.get("timestamp", "").strip()
                status = entry.get("status", "").strip()
                if not timestamp or not status:
                    continue
                if script and script_name != script:
                    continue
                if station and station_name != station:
                    continue
                rows.append(
                    {
                        "timestamp": timestamp,
                        "status": status,
                        "script": script_name,
                        "station": station_name or "",
                        "source": str(csv_path.relative_to(root)),
                    }
                )
    rows.sort(key=lambda item: item["timestamp"])
    return rows


def write_csv(rows: Iterable[Dict[str, str]], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["timestamp", "status", "script", "station", "source"]
    with destination.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


class _StatusHandler(BaseHTTPRequestHandler):
    def _write(self, payload: bytes, content_type: str = "text/plain") -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # type: ignore[override]
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        script = params.get("script", [None])[0]
        station = params.get("station", [None])[0]
        rows = collect_status_rows(REPO_ROOT, script=script, station=station)
        if parsed.path.endswith(".json"):
            payload = json.dumps(rows).encode("utf-8")
            self._write(payload, "application/json")
        else:
            fieldnames = ["timestamp", "status", "script", "station", "source"]
            buffer = [",".join(fieldnames)]
            for row in rows:
                buffer.append(
                    ",".join(row.get(col, "") for col in fieldnames)
                )
            payload = "\n".join(buffer).encode("utf-8")
            self._write(payload, "text/csv")

    def log_message(self, format: str, *args) -> None:  # type: ignore[override]
        return


def cmd_build(output: Path) -> None:
    rows = collect_status_rows(REPO_ROOT)
    write_csv(rows, output)
    print(f"Wrote {len(rows)} rows to {output}")


def cmd_serve(port: int) -> None:
    server = ThreadingHTTPServer(("0.0.0.0", port), _StatusHandler)
    print(f"Serving status data on http://localhost:{port}/status_timeseries.csv")
    print(f"JSON endpoint available at http://localhost:{port}/status_timeseries.json")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping server…")


def _parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Status dashboard utilities")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="Generate aggregated CSV")
    build.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)

    serve = sub.add_parser("serve", help="Serve CSV/JSON endpoints")
    serve.add_argument("--port", type=int, default=8050)

    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    if args.command == "build":
        cmd_build(args.output)
        return 0
    if args.command == "serve":
        cmd_serve(args.port)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
