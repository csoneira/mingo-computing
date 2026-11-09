#!/usr/bin/env python3
"""Verify and redirect simulation INTERSTEPS to configured external storage."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[5]
CONFIG = ROOT / "CONTEXTUAL/CONFIG/CONTENTS/storage/external_storage.conf"


def read_config(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator:
            raise ValueError(f"Invalid storage config line: {line!r}")
        values[key.strip()] = value.strip().strip("\"'")
    return values


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inventory(root: Path) -> dict[str, tuple[int, str]]:
    result: dict[str, tuple[int, str]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Refusing to relocate a tree containing a symlink: {path}")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = (path.stat().st_size, file_digest(path))
        elif not path.is_dir():
            raise ValueError(f"Refusing non-regular entry: {path}")
    return result


def exchange(left: Path, right: Path) -> None:
    import ctypes

    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise RuntimeError("Linux renameat2 is required for safe INTERSTEPS cutover")
    if renameat2(-100, os.fsencode(left), -100, os.fsencode(right), 2) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def active_simulation_processes() -> list[str]:
    found: list[str] = []
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit() or int(proc.name) == os.getpid():
            continue
        try:
            args = [os.fsdecode(part) for part in (proc / "cmdline").read_bytes().split(b"\0") if part]
        except OSError:
            continue
        command = " ".join(args)
        if any(
            marker in command
            for marker in (
                "run_main_simulation_cycle.sh",
                "run_step.sh",
                "step_final_daq_to_station_dat.py",
            )
        ) or any(Path(arg).name.startswith("step_") and Path(arg).suffix == ".py" for arg in args):
            found.append(f"PID {proc.name}: {command[:220]}")
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storage-config", type=Path, default=CONFIG)
    parser.add_argument("--activate", action="store_true", help="Copy, verify, and atomically redirect INTERSTEPS")
    args = parser.parse_args()
    settings = read_config(args.storage_config)
    if settings.get("USE_EXTERNAL_SIM_INTERSTEPS", "0") != "1":
        parser.error("External simulation INTERSTEPS are disabled in the storage config")

    external_root = Path(settings.get("EXTERNAL_STORAGE_ROOT", "/home/data/mingo")).expanduser()
    relative_destination = Path(settings.get("EXTERNAL_SIM_INTERSTEPS_DIR", "SIMULATION_INTERSTEPS"))
    if relative_destination.is_absolute() or ".." in relative_destination.parts:
        parser.error("EXTERNAL_SIM_INTERSTEPS_DIR must be a safe path relative to EXTERNAL_STORAGE_ROOT")
    source = ROOT / "PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/INTERSTEPS"
    destination = external_root / relative_destination
    if source.is_symlink():
        if source.resolve() == destination.resolve():
            print(f"INTERSTEPS already use external storage: {destination}")
            return 0
        parser.error(f"Unexpected existing INTERSTEPS symlink: {source} -> {source.resolve()}")
    if not source.is_dir():
        parser.error(f"INTERSTEPS source is missing: {source}")
    parent = destination.parent
    while not parent.exists() and parent != parent.parent:
        parent = parent.parent
    if parent.stat().st_dev == source.stat().st_dev:
        parser.error("Configured destination is not on a separate filesystem")
    if not os.access(parent, os.W_OK):
        parser.error(f"External destination parent is not writable: {parent}")

    source_inventory = inventory(source)
    total_bytes = sum(size for size, _ in source_inventory.values())
    print(f"INTERSTEPS: {len(source_inventory)} files, {total_bytes / 1024**3:.3f} GiB")
    print(f"Source:      {source}")
    print(f"Destination: {destination}")
    if not args.activate:
        print("Read-only inventory only. Use --activate after simulation jobs are quiescent.")
        return 0

    state = ROOT / "CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/STATE/simulation_intersteps_offload"
    state.mkdir(parents=True, exist_ok=True)
    lock_paths = [
        ROOT / "CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/LOCKS/cron/sim_enqueue.lock",
        ROOT / "CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/LOCKS/cron/sim_processing.lock",
        ROOT / "CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/LOCKS/cron/sim_final.lock",
    ]
    locks = []
    try:
        for lock_path in lock_paths:
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            lock = lock_path.open("a")
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                lock.close()
                raise RuntimeError(f"Simulation phase is active (lock busy): {lock_path}") from exc
            locks.append(lock)
        active = active_simulation_processes()
        if active:
            raise RuntimeError("Simulation writers are active; no cutover performed:\n" + "\n".join(active))
        if destination.exists() or destination.is_symlink():
            raise RuntimeError(f"Destination already exists; preserving it: {destination}")
        if inventory(source) != source_inventory:
            raise RuntimeError("INTERSTEPS changed after inventory; no cutover performed")
        staging = Path(tempfile.mkdtemp(prefix=".SIMULATION_INTERSTEPS.copy-", dir=destination.parent))
        try:
            source_dirs = sorted(
                (path for path in source.rglob("*") if path.is_dir()),
                key=lambda path: len(path.relative_to(source).parts),
            )
            for source_dir in source_dirs:
                relative = source_dir.relative_to(source)
                (staging / relative).mkdir(parents=True, exist_ok=True)
            for rel, (size, digest) in source_inventory.items():
                src = source / rel
                out = staging / rel
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, out)
                if out.stat().st_size != size or file_digest(out) != digest:
                    raise RuntimeError(f"Copy verification failed: {rel}")
            for source_dir in reversed(source_dirs):
                shutil.copystat(source_dir, staging / source_dir.relative_to(source))
            shutil.copystat(source, staging)
            if inventory(staging) != source_inventory:
                raise RuntimeError("External copy inventory differs from source")
            if inventory(source) != source_inventory:
                raise RuntimeError("INTERSTEPS changed while copying; original preserved")
            os.rename(staging, destination)
            fsync_directory(destination.parent)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise

        link = source.with_name(f".INTERSTEPS.external-link-{time.time_ns()}")
        link.symlink_to(destination, target_is_directory=True)
        try:
            exchange(source, link)
            fsync_directory(source.parent)
        except Exception:
            link.unlink(missing_ok=True)
            raise
        try:
            if inventory(link) != source_inventory or inventory(destination) != source_inventory:
                raise RuntimeError(f"Post-cutover verification failed; original preserved at {link}")
            shutil.rmtree(link)
        except Exception:
            raise
        print(f"Activated external INTERSTEPS at {destination}")
        return 0
    finally:
        for lock in reversed(locks):
            lock.close()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError) as error:
        print(f"External INTERSTEPS relocation stopped: {error}", file=sys.stderr)
        sys.exit(2)
