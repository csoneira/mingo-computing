#!/usr/bin/env python3
"""Plan explicit cleanup categories. Never follow symlinks or touch processing/metadata.

No pressure-triggered fallback: every deletion must belong to a selected category.
"""
import argparse
import collections
import fcntl
import json
import math
import os
from pathlib import Path
import stat
import subprocess
import sys
import time

_REPO_IMPORT_ROOT = Path(__file__).resolve().parents[5]
if str(_REPO_IMPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_IMPORT_ROOT))
from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.path_config import get_repo_root

HERE = Path(__file__).resolve().parent
CATEGORIES = {'plots', 'pdfs', 'pngs', 'temps', 'completed_data', 'error_data', 'unprocessed_data',
              'parquet_lake', 'simulation_intermediates', 'simulation_junk'}
ALIASES = {'completed': 'completed_data'}
PLOT_DIRS = {'PLOTS', 'DEBUG_PLOTS', 'FINAL_PLOTS', 'FIGURE_DIRECTORY', 'PDF_DIRECTORY'}
PROTECTED = {'METADATA', 'PROCESSING', 'PROCESSING_DIRECTORY', '.GIT', '.VENV'}
DATA_EXTENSIONS = {'.parquet', '.dat', '.hld', '.gz', '.pkl', '.pickle', '.csv', '.txt', '.json'}


def load_config(path):
    config = json.loads(path.read_text())
    if config.get('version') != 1:
        raise ValueError('Unsupported cleaner config version')
    if type(config.get('check_archive_consistency')) is not bool:
        raise ValueError('check_archive_consistency must be boolean')
    threshold = config.get('disk_threshold_percent')
    if type(threshold) not in (int, float) or not math.isfinite(threshold) or not 0 <= threshold <= 100:
        raise ValueError('disk_threshold_percent must be between 0 and 100')
    rules = config.get('categories', {})
    if set(rules) != CATEGORIES:
        raise ValueError(f'Categories must be exactly {sorted(CATEGORIES)}')
    for category, rule in rules.items():
        if set(rule) != {'enabled', 'min_age_hours', 'keep_newest'} or type(rule['enabled']) is not bool:
            raise ValueError(f'{category}: invalid rule or enabled flag')
        age, keep = rule['min_age_hours'], rule['keep_newest']
        if type(age) not in (int, float) or not math.isfinite(age) or age < 0:
            raise ValueError(f'{category}: invalid min_age_hours')
        if type(keep) is not int or keep < 0:
            raise ValueError(f'{category}: invalid keep_newest')
    return config


def safe_path(path, root):
    try:
        rel = path.relative_to(root)
    except ValueError:
        return False
    if any(part.upper() in PROTECTED for part in rel.parts):
        return False
    current = root
    for part in rel.parts:
        current /= part
        if current.is_symlink():
            return False
    return True


def walk_files(base, root):
    if not safe_path(base, root) or not base.is_dir():
        return
    for directory, dirs, files in os.walk(base, followlinks=False):
        parent = Path(directory)
        dirs[:] = sorted(d for d in dirs if safe_path(parent / d, root))
        for name in sorted(files):
            p = parent / name
            if safe_path(p, root):
                try:
                    st = p.lstat()
                except FileNotFoundError:
                    continue
                if stat.S_ISREG(st.st_mode):
                    yield p, st


def plot_bundle(path):
    # Rank complete runtime runs or final parquet reports, never individual panels.
    parts = path.parts
    for i, part in enumerate(parts[:-1]):
        if part in {'DEBUG_PLOTS', 'FIGURE_DIRECTORY'} and i + 2 < len(parts):
            return Path(*parts[:i+2])
        if part == 'FINAL_PLOTS':
            j = i + 2 if i + 1 < len(parts) and parts[i+1].startswith('TASK_') else i + 1
            if j + 1 < len(parts):
                return Path(*parts[:j+1])
    return path  # Loose plots rank as individual files within their directory.


def classify(path, root):
    rel = path.relative_to(root)
    parts = rel.parts
    upper = [p.upper() for p in parts]
    suffix = path.suffix.lower()
    station = len(parts) > 2 and parts[:3] == ('PIPELINE', 'MINGO_ANALYSIS', 'MINGO_ANALYSIS_STATIONS')
    simulation = parts[:3] == ('PIPELINE', 'MINGO_DIGITAL_TWIN', 'SIMULATION_OUTPUTS')
    ancillary = parts[:4] == ('PIPELINE', 'MINGO_ANALYSIS', 'MINGO_ANALYSIS_SCRIPTS', 'ANCILLARY')
    sim_plots = parts[:3] == ('PIPELINE', 'MINGO_DIGITAL_TWIN', 'PLOTTERS')
    if (station or simulation or ancillary or sim_plots) and any(p in PLOT_DIRS for p in upper):
        if suffix in {'.png', '.pdf', '.svg', '.jpg', '.jpeg', '.eps'}:
            return 'plot', plot_bundle(path)
    if station:
        if 'COMPLETED' in upper or 'COMPLETED_DIRECTORY' in upper:
            if suffix in DATA_EXTENSIONS:
                return 'completed_data', path
        if 'ERROR' in upper or 'ERROR_DIRECTORY' in upper:
            if suffix in DATA_EXTENSIONS:
                return 'error_data', path
        if 'UNPROCESSED' in upper or 'UNPROCESSED_DIRECTORY' in upper:
            if suffix in DATA_EXTENSIONS:
                return 'unprocessed_data', path
        if 'PARQUET_LAKE' in upper and suffix == '.parquet':
            return 'parquet_lake', path
    if simulation and 'INTERSTEPS' in upper:
        # Whole SIM_RUN directories only: a mesh/manifest is never partly removed.
        for i, part in enumerate(parts):
            if part.startswith('SIM_RUN_'):
                return 'simulation_intermediates', root.joinpath(*parts[:i+1])
    if parts[0] == 'SIMULATION_DATA_JUNK':
        return 'simulation_junk', path
    if 'daqData' in parts:
        tail = parts[parts.index('daqData') + 1:]
        if (len(tail) > 1 and tail[0] == 'varData') or tail[:3] in (
            ('rawData', 'dat', 'done'), ('rawData', 'dat', 'removed')) or tail[:2] == ('asci', 'removed'):
            return 'temps', path
    return None, None


def scan(root, selected, rules, now=None, keep_final=False):
    now = time.time() if now is None else now
    groups = collections.defaultdict(list)
    bases = [root/'PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS',
             root/'PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS', root/'SIMULATION_DATA_JUNK',
             root/'PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY',
             root/'PIPELINE/MINGO_DIGITAL_TWIN/PLOTTERS']
    if 'temps' in selected:
        bases.append(root/'PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0')
    for base in bases:
        for p, st in walk_files(base, root):
            category, bundle = classify(p, root)
            if category == 'plot':
                # plots is shorthand for all figure formats; deduplicate overlapping switches.
                category = next((c for c in ('plots', 'pdfs', 'pngs') if c in selected and
                                 (c == 'plots' or p.suffix.lower() == { 'pdfs': '.pdf', 'pngs': '.png'}[c])), None)
            if category not in selected or (keep_final and category == 'completed_data'):
                continue
            groups[(category, bundle.parent)].append((bundle, p, st))
    candidates = []
    for (category, parent), entries in groups.items():
        bundles = collections.defaultdict(list)
        for bundle, p, st in entries:
            bundles[bundle].append((p, st))
        # Include every file's mtime when retaining a report, even if only PDFs/PNGs selected.
        newest = {}
        for bundle, files in bundles.items():
            newest[bundle] = max(st.st_mtime for p, st in files)
            if bundle.is_dir():
                newest[bundle] = max([newest[bundle]] + [st.st_mtime for p, st in walk_files(bundle, root)])
        ranked = sorted(bundles, key=lambda b: (-newest[b], str(b)))
        rule = rules[category]
        for bundle in ranked[rule['keep_newest']:]:
            if now - newest[bundle] < rule['min_age_hours'] * 3600:
                continue
            for p, st in bundles[bundle]:
                candidates.append((category, p, st))
    # Files currently claimed by a task are protected in every category.
    import re
    active = set()
    stations = root/'PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS'
    for directory, dirs, files in os.walk(stations, followlinks=False):
        parent = Path(directory)
        dirs[:] = [d for d in dirs if not (parent/d).is_symlink() and d not in {'METADATA','PLOTS','PARQUET_LAKE'}]
        if parent.name in {'PROCESSING', 'PROCESSING_DIRECTORY'}:
            for name in files:
                active.update(re.findall(r'mi[0-9]{13}', name))
    tracked_result = subprocess.run(['git', '-C', str(root), 'ls-files', '-z'], capture_output=True)
    tracked = set(os.fsdecode(tracked_result.stdout).split('\0')) if tracked_result.returncode == 0 else set()
    return sorted((item for item in candidates if str(item[1].relative_to(root)) not in tracked
                   and not any(name in str(item[1]) for name in active)), key=lambda item: str(item[1]))


def delete_candidate(path, before, root):
    # Traverse using directory descriptors with O_NOFOLLOW to resist symlink swaps.
    parts = path.relative_to(root).parts
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = nxt
        current = os.stat(parts[-1], dir_fd=fd, follow_symlinks=False)
        signature = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
        if not stat.S_ISREG(current.st_mode) or signature(current) != signature(before):
            return False
        os.unlink(parts[-1], dir_fd=fd)
        return True
    finally:
        os.close(fd)


def prune_empty_plot_directories(root, target_path=None):
    """Remove empty descendants within generated plot folders, then empty roots."""
    target_names = {'FIGURE_DIRECTORY', 'DEBUG_PLOTS'}
    bases = [root/'PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS',
             root/'PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS',
             root/'PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY',
             root/'PIPELINE/MINGO_DIGITAL_TWIN/PLOTTERS']
    if target_path is not None:
        target_path = Path(target_path)
        targets = {target_path} if target_path.name in target_names else set()
    else:
        targets = set()
        for base in bases:
            if not safe_path(base, root) or not base.is_dir():
                continue
            for directory, dirs, _ in os.walk(base, topdown=True, followlinks=False):
                parent = Path(directory)
                dirs[:] = sorted(d for d in dirs if safe_path(parent/d, root))
                targets.update(parent/name for name in dirs if name in target_names)

    removed = 0
    for target in sorted(targets, key=lambda p: len(p.parts), reverse=True):
        if not safe_path(target, root) or not target.is_dir():
            continue
        # Prune only empty descendants inside this generated figure directory.
        for directory, dirs, _ in os.walk(target, topdown=False, followlinks=False):
            current = Path(directory)
            if not safe_path(current, root):
                continue
            dirs[:] = [d for d in dirs if safe_path(current/d, root)]
            for child in dirs:
                try:
                    (current/child).rmdir()
                    removed += 1
                except OSError:
                    pass
            try:
                current.rmdir()
                removed += 1
            except OSError:
                pass
    return removed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=get_repo_root())
    parser.add_argument('--config', type=Path, default=HERE/'cleaner_config.json')
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--apply', action='store_true', help='Delete eligible files; default is dry-run')
    action.add_argument('--dry-run', action='store_true')
    parser.add_argument('--force', '-f', action='store_true', help='Bypass disk threshold, not age/retention')
    parser.add_argument('--threshold', '-t', type=float)
    parser.add_argument('--select', '-s', action='append', help='Explicit category override (comma separated); otherwise use enabled categories')
    parser.add_argument('--compact', '-c', action='store_true')
    parser.add_argument('--keep-final', action='store_true', help='Always preserve completed_data')
    parser.add_argument('--report', type=Path, help='Write candidate CSV including byte sizes')
    args = parser.parse_args()
    root = args.root.resolve()
    if not (root/"CONTEXTUAL" / "CONFIG").is_dir() or not (root/"PIPELINE" / "MINGO_ANALYSIS").is_dir():
        parser.error('Root must contain CONTEXTUAL/CONFIG and PIPELINE/MINGO_ANALYSIS')
    config = load_config(args.config)
    selected = {c for c,r in config['categories'].items() if r['enabled']}
    if args.select:
        tokens = {t.strip() for entry in args.select for t in entry.split(',')}
        selected = {ALIASES.get(t,t) for t in tokens}
        if 'all' in selected:
            parser.error('--select all is unsafe; name each category explicitly')
    if selected - CATEGORIES:
        parser.error(f'Unknown categories: {sorted(selected-CATEGORIES)}')
    threshold = config['disk_threshold_percent'] if args.threshold is None else args.threshold
    if not math.isfinite(threshold) or not 0 <= threshold <= 100:
        parser.error('Threshold must be between 0 and 100')
    # Same persistent lock as the previous shell cleaner; never unlink a live lock inode.
    lock = Path(os.environ.get('DATAFLOW_CLEAN_LOCK_FILE', '/tmp/dataflow_clean_dataflow.lock'))
    with lock.open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('Another cleaner holds the lock; skipped.'); return 0
        usage = os.statvfs(root)
        percent = 100*(usage.f_blocks-usage.f_bfree)/(usage.f_blocks-usage.f_bfree+usage.f_bavail)
        print(f"{'APPLY' if args.apply else 'DRY RUN'} root={root} selected={','.join(sorted(selected))} disk={percent:.1f}%")
        if not args.force and percent < threshold:
            print(f'Below threshold {threshold}%; skipped.'); return 0
        simulation_locks = []
        if selected & {'simulation_intermediates', 'simulation_junk'}:
            for name in ('sim_enqueue.lock', 'sim_processing.lock', 'sim_final.lock'):
                lockpath = root/'CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/LOCKS/cron'/name
                lockpath.parent.mkdir(parents=True, exist_ok=True)
                h = lockpath.open('a')
                simulation_locks.append(h)
                try:
                    fcntl.flock(h, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    print('Simulation is active; refusing simulation cleanup.'); return 2
        candidates = scan(root, selected, config['categories'], keep_final=args.keep_final)
        if args.report:
            import csv
            with args.report.open('w') as f:
                writer=csv.writer(f);writer.writerow(['category','bytes','path'])
                writer.writerows((c,s.st_size,str(p)) for c,p,s in candidates)
        totals = collections.defaultdict(lambda: [0,0])
        failures = 0
        for category, path, before in candidates:
            if args.apply:
                try:
                    if not safe_path(path, root) or not delete_candidate(path,before,root):
                        print(f'SKIP changed/unsafe file: {path}'); continue
                except OSError as exc:
                    print(f'ERROR deleting {path}: {exc}',file=sys.stderr);failures+=1;continue
            totals[category][0]+=1; totals[category][1]+=before.st_size
            if not args.compact: print(f'{category}\t{before.st_size}\t{path}')
        for category,(count,size) in sorted(totals.items()):
            print(f'{category}: {count} files, {size/1024**3:.3f} GiB '+('deleted' if args.apply else 'eligible'))
        if args.apply and selected & {'plots', 'pdfs', 'pngs'}:
            removed_dirs = prune_empty_plot_directories(root)
            print(f'Empty DEBUG_PLOTS/FIGURE_DIRECTORY folders removed: {removed_dirs}')
        print(f'Total: {sum(v[1] for v in totals.values())/1024**3:.3f} GiB; errors={failures}')
        if args.apply and config['check_archive_consistency']:
            env=dict(os.environ,DATAFLOW_CLEAN_ROOT=str(root))
            result=subprocess.run(['bash',str(HERE/'check_parquet_lake_consistency.sh')],env=env)
            failures+=result.returncode != 0
        return int(bool(failures))

if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f'Cleaner refused: {exc}',file=sys.stderr);sys.exit(2)
