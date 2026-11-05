#!/usr/bin/env python3
"""Venv-side configuration checks; no production script execution."""
import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import urllib.request
import yaml

ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / 'PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/CONFIG_FILES'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--restore-logbooks', action='store_true')
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args()
    results = []
    files = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    invalid = []
    for name in files:
        # MkDocs uses Python YAML tags; MkDocs itself validates that file.
        if name.endswith(('.yaml', '.yml')) and name != 'DOCUMENTATION/mkdocs.yml':
            try: yaml.safe_load((ROOT / name).read_text())
            except Exception: invalid.append(name)
    results.append((not invalid, 'Tracked YAML parses' + (': ' + ', '.join(invalid) if invalid else '')))
    c = yaml.safe_load((CONFIG / 'STAGE_0/NEW_FILES/config_new_files.yaml').read_text())['logbook']
    for station, gid in c['gid_by_station'].items():
        path = CONFIG / f'STAGE_0/ONLINE_RUN_DICTIONARY/STATION_{station}/input_file_mingo0{station}.csv'
        url = f"https://docs.google.com/spreadsheets/d/{c['sheet_id']}/export?format=csv&gid={gid}"
        if not args.offline:
            try:
                with urllib.request.urlopen(url, timeout=12) as stream:
                    data = stream.read(2_000_001)
                if len(data) > 2_000_000: raise ValueError('Oversize logbook')
                rows = list(csv.reader(io.StringIO(data.decode('utf-8-sig'))))
                valid = len(rows) > 2 and {'start', 'end', 'P1', 'P2', 'P3', 'P4'}.issubset(rows[1])
                results.append((valid, f'Station {station}: HTTPS Google logbook and second-row CSV schema'))
                if valid and args.restore_logbooks and not path.exists():
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with path.open('xb') as output: output.write(data)
                    path.chmod(0o600)
            except Exception:
                results.append((False, f'Station {station}: Google logbook download/schema unavailable'))
        try:
            with path.open(newline='') as stream:
                rows = list(csv.reader(stream))
            valid = len(rows) > 2 and {'start', 'end', 'P1', 'P2', 'P3', 'P4'}.issubset(rows[1])
        except OSError: valid = False
        results.append((valid, f'Station {station}: restored local online-run dictionary CSV'))
    c = yaml.safe_load((CONFIG / 'STAGE_0/REPROCESSING/config_reprocessing.yaml').read_text())
    retry = c.get('qa_retry', {})
    if retry.get('enabled'):
        path = Path(retry.get('source_csv', '')).expanduser()
        if not path.is_absolute(): path = Path.home() / path
        results.append((path.is_file(), 'QA retry is enabled: restore/rebuild the real QA summary before reprocessing: ' + str(path)))
    print(json.dumps(results))
    return int(any(not ok for ok, _ in results))


if __name__ == '__main__': raise SystemExit(main())
