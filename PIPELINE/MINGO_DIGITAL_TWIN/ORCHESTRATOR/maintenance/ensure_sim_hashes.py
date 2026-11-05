#!/usr/bin/env python3
"""
DATAFLOW_v3 Script Header v1
Script: PIPELINE/MINGO_DIGITAL_TWIN/ORCHESTRATOR/maintenance/ensure_sim_hashes.py
Purpose: Ensure simulation metadata and outputs contain consistent parameter hashes.
Owner: DATAFLOW_v3 contributors
Sign-off: csoneira <csoneira@ucm.es>
Last Updated: 2026-03-02
Runtime: python3
Usage: python3 PIPELINE/MINGO_DIGITAL_TWIN/ORCHESTRATOR/maintenance/ensure_sim_hashes.py [options]
Inputs: CLI args, config files, environment variables, and/or upstream files.
Outputs: Files, logs, plots, or stdout/stderr side effects.
Notes: Keep behavior configuration-driven and reproducible.
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

import pandas as pd
import warnings

# pyarrow is optional; many operations depend on it for parquet work
try:
    import pyarrow as pa
    import pyarrow.parquet as pq
    import pyarrow.compute as pc
except ImportError:  # pragma: no cover - fall back for environments without arrow
    pq = None
    pc = None
    warnings.warn(
        "pyarrow not installed; parquet operations will fall back to slower or limited "
        "behavior.  Install pyarrow to improve performance.",
        RuntimeWarning,
    )

# small helper for reading column data with pyarrow or pandas

def parse_first_line_hash(line: str) -> Optional[str]:
    if not line:
        return None
    stripped = line.strip()
    if not stripped.startswith("#"):
        return None
    if stripped.lower().startswith("# param_hash="):
        value = stripped.split("=", 1)[1].strip()
        return value or None
    return None


def load_param_hash_lookup(params_path: Path) -> Dict[str, str]:
    lookup: Dict[str, str] = {}
    if not params_path.exists():
        return lookup
    with params_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            file_name = (row.get("file_name") or "").strip()
            param_hash = (row.get("param_hash") or "").strip()
            if not file_name or not param_hash:
                continue
            lookup[file_name.lower()] = param_hash
    return lookup


def load_param_hash_set(params_path: Path) -> set[str]:
    hashes: set[str] = set()
    if not params_path.exists():
        return hashes
    with params_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            param_hash = (row.get("param_hash") or "").strip()
            if not param_hash:
                continue
            hashes.add(param_hash)
    return hashes


def iter_mi00_files(roots: Iterable[Path]) -> Iterable[Path]:
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("mi00*.dat"):
            if path.is_file():
                yield path


def iter_mi00_parquets(roots: Iterable[Path]) -> Iterable[Path]:
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.parquet"):
            if path.is_file() and "mi00" in path.name.lower():
                yield path


def normalize_hash(value: object) -> Optional[str]:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    text = str(value).strip()
    return text or None


def extract_mi00_basename(path: Path) -> Optional[str]:
    match = re.search(r"(mi00\d+)", path.name.lower())
    if not match:
        return None
    return match.group(1)


def lookup_param_hash_for_parquet(path: Path, lookup: Dict[str, str]) -> Optional[str]:
    basename = extract_mi00_basename(path)
    if not basename:
        return None
    return lookup.get(f"{basename}.dat")


def parquet_hash_status(path: Path) -> Tuple[str, Optional[str]]:
    """Return status and (possible) hash for a parquet file.

    The previous implementation iterated row‑group by row‑group, calling
    ``read_row_group`` for every group.  That resulted in a lot of Python
    overhead and many small reads when tens or hundreds of files are being
    checked.  A single ``read`` of the ``param_hash`` column is significantly
    faster, especially on modern SSDs and when using the PyArrow C++ code to
    filter/null‑check the column.
    """

    if pq is None:  # pyarrow not installed
        return "error_read", None

    try:
        parquet = pq.ParquetFile(path)
    except Exception:
        return "error_read", None

    if "param_hash" not in parquet.schema.names:
        return "missing_column", None

    try:
        # read the entire column at once rather than iterating row groups
        table = parquet.read(columns=["param_hash"])
        col = table.column(0)
        # use Arrow compute where possible to reduce Python looping
        # convert to python objects because normalize_hash already handles
        # pandas-style NaN etc.
        values = col.to_pylist()
        found_value = None
        found_missing = False
        for value in values:
            normalized = normalize_hash(value)
            if normalized:
                if found_value is None:
                    found_value = normalized
            else:
                found_missing = True
    except Exception:
        return "error_read", None

    if found_value and found_missing:
        return "needs_fill", found_value
    if found_value:
        return "has_hash", found_value
    return "empty_column", None


def ensure_param_hash_column(path: Path, param_hash: str, apply_changes: bool) -> bool:
    """Make sure the parquet has a non‑empty ``param_hash`` for every row.

    The original version round‑tripped the file through pandas which was
    convenient but fairly slow: parquet → pandas DataFrame → parquet.  When
    the only modification is filling a single column, doing it in pure
    PyArrow saves both memory and CPU time.  We still keep the ``apply_changes``
    guard so dry‑runs are cheap.
    """

    if not apply_changes:
        return True
    if pq is None:
        # nothing we can do without pyarrow; pretend it succeeded so the
        # caller can continue to other files
        return True

    tmp_path = path.with_suffix(path.suffix + ".tmp")
    # load ahead of time so we can examine schema
    table = pq.read_table(path)

    if "param_hash" not in table.column_names:
        # create a column full of the given hash
        nrows = table.num_rows
        newcol = pa.array([param_hash] * nrows)
        table = table.append_column("param_hash", newcol)
    else:
        col = table.column("param_hash")
        # mask of rows that are null/empty after stripping
        mask = pc.is_null(col) | pc.equal(pc.utf8_trim_whitespace(pc.cast(col, pa.string())), "")
        if not pc.any(mask).as_py():
            return True  # nothing to fill
        filled = pc.if_else(mask, pa.array([param_hash] * table.num_rows), col)
        table = table.set_column(table.schema.get_field_index("param_hash"), "param_hash", filled)

    pq.write_table(table, tmp_path, compression="zstd")
    tmp_path.replace(path)
    return True


def ensure_hash_header(path: Path, param_hash: str, apply_changes: bool) -> bool:
    header = f"# param_hash={param_hash}\n".encode("ascii")
    if not apply_changes:
        return True
    tmp_path = path.with_name(f"{path.name}.tmp")
    with tmp_path.open("wb") as out_handle:
        out_handle.write(header)
        with path.open("rb") as in_handle:
            shutil.copyfileobj(in_handle, out_handle)
    tmp_path.replace(path)
    return True


def remove_file(path: Path, apply_changes: bool) -> bool:
    if not apply_changes:
        return True
    path.unlink()
    return True


def process_file(
    path: Path,
    lookup: Dict[str, str],
    valid_hashes: set[str],
    apply_changes: bool,
) -> Tuple[str, Optional[str]]:
    try:
        with path.open("r", encoding="ascii", errors="replace") as handle:
            first_line = handle.readline()
    except OSError:
        return "error_read", None

    existing_hash = parse_first_line_hash(first_line)
    if existing_hash:
        if valid_hashes and existing_hash not in valid_hashes:
            try:
                remove_file(path, apply_changes)
                return "deleted_hash_mismatch", existing_hash
            except OSError:
                return "error_delete", existing_hash
        return "has_hash", existing_hash

    lookup_hash = lookup.get(path.name.lower())
    if lookup_hash:
        try:
            ensure_hash_header(path, lookup_hash, apply_changes)
            return "added_hash", lookup_hash
        except OSError:
            return "error_write", lookup_hash

    try:
        remove_file(path, apply_changes)
        return "deleted", None
    except OSError:
        return "error_delete", None


def process_parquet(
    path: Path,
    lookup: Dict[str, str],
    valid_hashes: set[str],
    apply_changes: bool,
) -> Tuple[str, Optional[str]]:
    status, detail = parquet_hash_status(path)
    if status == "has_hash":
        if detail and valid_hashes and detail not in valid_hashes:
            try:
                remove_file(path, apply_changes)
                return "parquet_deleted_hash_mismatch", detail
            except OSError:
                return "parquet_error_delete", detail
        return "parquet_has_hash", detail
    if status == "needs_fill" and detail:
        if valid_hashes and detail not in valid_hashes:
            try:
                remove_file(path, apply_changes)
                return "parquet_deleted_hash_mismatch", detail
            except OSError:
                return "parquet_error_delete", detail
        try:
            ensure_param_hash_column(path, detail, apply_changes)
            return "parquet_filled_hash", detail
        except OSError:
            return "parquet_error_write", detail
    if status == "error_read":
        return "parquet_error_read", None

    lookup_hash = lookup_param_hash_for_parquet(path, lookup)
    if not lookup_hash:
        try:
            remove_file(path, apply_changes)
            return "parquet_deleted", None
        except OSError:
            return "parquet_error_delete", None
    if valid_hashes and lookup_hash not in valid_hashes:
        try:
            remove_file(path, apply_changes)
            return "parquet_deleted_hash_mismatch", lookup_hash
        except OSError:
            return "parquet_error_delete", lookup_hash

    try:
        ensure_param_hash_column(path, lookup_hash, apply_changes)
        return "parquet_added_hash", lookup_hash
    except OSError:
        return "parquet_error_write", lookup_hash


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Ensure mi00*.dat files include a param_hash header line. "
            "Ensure mi00*.parquet files include a param_hash column. "
            "If missing, attempt to insert from step_final_simulation_params.csv; "
            "otherwise delete the .dat file."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes (write headers and delete files). Default is dry-run.",
    )
    parser.add_argument(
        "--params",
        type=Path,
        default=None,
        help="Path to step_final_simulation_params.csv (optional).",
    )
    parser.add_argument(
        "--root",
        action="append",
        type=Path,
        default=[],
        help="Additional root directories to scan (optional).",
    )
    parser.add_argument(
        "--run-validate-quick",
        action="store_true",
        help=(
            "After hash checks, run validation quick set "
            "(cross,0,1,2,3 by default)."
        ),
    )
    parser.add_argument(
        "--validate-quick-steps",
        default="cross,0,1,2,3",
        help="Step selector passed to VALIDATION/run_validation.py when using --run-validate-quick.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[4]
    default_params = (
        repo_root
        / "PIPELINE" / "MINGO_DIGITAL_TWIN"
        / "SIMULATION_OUTPUTS"
        / "SIMULATED_DATA"
        / "step_final_simulation_params.csv"
    )

    if pq is None:
        # give a clearer runtime warning in the top‐level invocation as well
        print("WARNING: pyarrow not available; parquet processing will be slower or less complete.")
    params_path = args.params or default_params
    lookup = load_param_hash_lookup(params_path)
    valid_hashes = load_param_hash_set(params_path)

    roots = [
        repo_root
        / "PIPELINE" / "MINGO_DIGITAL_TWIN"
        / "SIMULATION_OUTPUTS"
        / "SIMULATED_DATA",
        repo_root / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_STATIONS" / "MINGO00",
    ]
    roots.extend(args.root)

    stats = {
        "checked": 0,
        "has_hash": 0,
        "added_hash": 0,
        "deleted": 0,
        "deleted_hash_mismatch": 0,
        "error_read": 0,
        "error_write": 0,
        "error_delete": 0,
        "parquet_checked": 0,
        "parquet_has_hash": 0,
        "parquet_filled_hash": 0,
        "parquet_added_hash": 0,
        "parquet_deleted": 0,
        "parquet_deleted_hash_mismatch": 0,
        "parquet_error_read": 0,
        "parquet_error_write": 0,
        "parquet_error_delete": 0,
    }

    # build lists up front so we can measure and parallelize the work
    dat_paths = list(iter_mi00_files(roots))
    parquet_paths = list(iter_mi00_parquets(roots))

    # use a thread pool for I/O-bound operations; the work is largely
    # reading/parsing files on disk so threads are sufficient and avoid the
    # overhead of spawning processes.
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading

    lock = threading.Lock()

    def handle_dat(path: Path):
        status, detail = process_file(path, lookup, valid_hashes, args.apply)
        with lock:
            stats["checked"] += 1
            if status in stats:
                stats[status] += 1
        if status == "has_hash":
            return
        if status == "added_hash":
            action = "ADD" if args.apply else "WOULD_ADD"
            print(f"{action} {path} param_hash={detail}")
        elif status == "deleted_hash_mismatch":
            action = "DELETE" if args.apply else "WOULD_DELETE"
            print(f"{action} {path} hash_not_in_table={detail}")
        elif status == "deleted":
            action = "DELETE" if args.apply else "WOULD_DELETE"
            print(f"{action} {path}")
        elif status.startswith("error_"):
            print(f"ERROR {status} {path}")

    def handle_parquet(path: Path):
        status, detail = process_parquet(path, lookup, valid_hashes, args.apply)
        with lock:
            stats["parquet_checked"] += 1
            if status in stats:
                stats[status] += 1
        if status == "parquet_has_hash":
            return
        if status == "parquet_filled_hash":
            action = "FILL" if args.apply else "WOULD_FILL"
            print(f"{action} {path} param_hash={detail}")
        elif status == "parquet_added_hash":
            action = "ADD" if args.apply else "WOULD_ADD"
            print(f"{action} {path} param_hash={detail}")
        elif status == "parquet_deleted_hash_mismatch":
            action = "DELETE" if args.apply else "WOULD_DELETE"
            print(f"{action} {path} hash_not_in_table={detail}")
        elif status == "parquet_deleted":
            action = "DELETE" if args.apply else "WOULD_DELETE"
            print(f"{action} {path}")
        elif status.startswith("parquet_error_"):
            print(f"ERROR {status} {path}")

    # choose a reasonable number of threads; default to 8 or os.cpu_count()
    max_workers = min(8, (len(dat_paths) + len(parquet_paths)) or 1)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for p in dat_paths:
            futures.append(executor.submit(handle_dat, p))
        for p in parquet_paths:
            futures.append(executor.submit(handle_parquet, p))
        # wait for completion; any printouts happen in worker threads
        for _ in as_completed(futures):
            pass

    mode = "APPLY" if args.apply else "DRY_RUN"
    print(f"Mode: {mode}")
    print(
        "Checked: {checked} | Has hash: {has_hash} | Added: {added_hash} | Deleted: {deleted} | "
        "Deleted (hash mismatch): {deleted_hash_mismatch} | Read errors: {error_read} | "
        "Write errors: {error_write} | Delete errors: {error_delete}".format(
            **stats
        )
    )
    print(
        "Parquet checked: {parquet_checked} | Has hash: {parquet_has_hash} | Added: {parquet_added_hash} | "
        "Filled: {parquet_filled_hash} | Deleted: {parquet_deleted} | Deleted (hash mismatch): "
        "{parquet_deleted_hash_mismatch} | Read errors: {parquet_error_read} | Write errors: "
        "{parquet_error_write} | Delete errors: {parquet_error_delete}".format(**stats)
    )

    if args.run_validate_quick:
        validation_runner = repo_root / "PIPELINE" / "MINGO_DIGITAL_TWIN" / "VALIDATION" / "run_validation.py"
        if not validation_runner.exists():
            print(f"WARNING: validate-quick skipped (missing runner: {validation_runner})")
        else:
            cmd = [
                "python3",
                str(validation_runner),
                "--steps",
                str(args.validate_quick_steps),
            ]
            print(f"Running validate-quick: {' '.join(cmd)}")
            rc = subprocess.run(cmd, check=False).returncode
            if rc != 0:
                print(f"ERROR: validate-quick failed with rc={rc}")
                return rc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
