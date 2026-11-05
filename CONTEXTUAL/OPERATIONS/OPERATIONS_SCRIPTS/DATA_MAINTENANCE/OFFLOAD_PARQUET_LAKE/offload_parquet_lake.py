#!/usr/bin/env python3
"""Ancillary copy/verify/offload of whole lake directories. Never changes skip/config logic."""
import argparse
import ctypes
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[5]

def signature(path):
    s=path.stat();return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns)

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        while chunk:=f.read(8*1024*1024):h.update(chunk)
    return h.hexdigest()

def valid_parquet(path):
    with path.open('rb') as f:
        if f.read(4)!=b'PAR1':raise ValueError(f'Invalid parquet header: {path}')
        f.seek(-4,os.SEEK_END)
        if f.read(4)!=b'PAR1':raise ValueError(f'Invalid parquet footer: {path}')

def sync_file(source,dest,cached=None):
    before=signature(source);valid_parquet(source)
    if cached and list(before)==cached['source'] and dest.exists() and not dest.is_symlink() and list(signature(dest))==cached['destination']:
        return cached
    if dest.exists():
        if dest.is_symlink():raise ValueError(f'Refusing destination symlink: {dest}')
        if before[2]==dest.stat().st_size and digest(source)==digest(dest):
            if signature(source)!=before:raise RuntimeError(f'Source changed: {source}')
            return dict(source=list(before),destination=list(signature(dest)),sha256=digest(dest))
    # Source is authoritative; replace only our station/basename copy, never unrelated files.
    fd,tmp=tempfile.mkstemp(prefix='.copy-',dir=dest.parent)
    tmp=Path(tmp)
    try:
        h=hashlib.sha256()
        with os.fdopen(fd,'wb') as out,source.open('rb') as inp:
            while chunk:=inp.read(8*1024*1024):
                h.update(chunk);out.write(chunk)
            out.flush();os.fsync(out.fileno())
        if signature(source)!=before or h.hexdigest()!=digest(tmp):
            raise RuntimeError(f'Source changed/copy verification failed: {source}')
        valid_parquet(tmp);shutil.copystat(source,tmp);os.replace(tmp,dest)
        dfd=os.open(dest.parent,os.O_DIRECTORY);os.fsync(dfd);os.close(dfd)
        return dict(source=list(before),destination=list(signature(dest)),sha256=h.hexdigest())
    finally:tmp.unlink(missing_ok=True)

def exchange(a,b):
    libc=ctypes.CDLL(None,use_errno=True)
    renameat2=getattr(libc,'renameat2',None)
    if renameat2 is None:raise RuntimeError('Linux renameat2 required for atomic directory exchange')
    if renameat2(-100,os.fsencode(a),-100,os.fsencode(b),2)!=0:
        e=ctypes.get_errno();raise OSError(e,os.strerror(e))

def entries(source):
    result=[]
    for p in sorted(source.iterdir()):
        if p.is_symlink() or not p.is_file() or p.suffix!='.parquet':
            raise ValueError(f'Unexpected lake entry; preserve and investigate: {p}')
        result.append(p)
    return result

def activate(source,dest,verified,journal):
    # Caller must have paused task launchers, waited for writers, and closed the production gate.
    current=entries(source)
    if {p.name for p in current}!=set(verified):raise RuntimeError('Lake changed since verification')
    for p in current:
        if list(signature(p))!=verified[p.name]['source'] or list(signature(dest/p.name))!=verified[p.name]['destination']:
            raise RuntimeError(f'Lake changed since verification: {p}')
    old=source.with_name('.offload-original-'+source.name+'-'+str(time.time_ns()))
    old.symlink_to(dest,target_is_directory=True)
    exchange(source,old)  # source always exists: now a directory symlink; old holds originals.
    journal.write(json.dumps(dict(event='exchanged',source=str(source),dest=str(dest),originals=str(old)))+'\n');journal.flush();os.fsync(journal.fileno())
    # Delete only verified originals. Failures leave the backup directory for recovery.
    for p in entries(old):
        if list(signature(p))!=verified[p.name]['source'] or list(signature(dest/p.name))!=verified[p.name]['destination']:
            raise RuntimeError(f'Original changed after cutover; preserved at {old}')
        p.unlink()
    old.rmdir()
    dfd=os.open(source.parent,os.O_DIRECTORY);os.fsync(dfd);os.close(dfd)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--destination',type=Path,default=Path('/home/mingo/data/PARQUET_LAKES'))
    parser.add_argument('--stations',default='0,1,2,3,4')
    parser.add_argument('--apply',action='store_true',help='Copy and SHA256 verify; default is inventory only')
    parser.add_argument('--activate',action='store_true',help='Atomically redirect lake and remove verified originals; requires paused pipeline')
    args=parser.parse_args();root=args.root.resolve();dest=args.destination.resolve()
    if args.activate and not args.apply:parser.error('--activate requires --apply')
    if not (root/'CONFIG').is_dir():parser.error('Not a repository root')
    ids=[int(n) for n in args.stations.split(',')]
    if any(n<0 or n>99 for n in ids) or len(set(ids))!=len(ids):parser.error('Invalid/duplicate stations')
    parent=dest
    while not parent.exists():parent=parent.parent
    if parent.stat().st_dev==root.stat().st_dev:
        parser.error('Destination is on the source filesystem; offloading would free no space')
    if not os.access(parent,os.W_OK):parser.error('Destination is not writable')
    gate=root/'CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/SETUP/production-enabled'
    if args.activate and gate.exists():parser.error('Close production gate and pause launchers before --activate')
    if args.activate:
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit():continue
            try:cmd=(proc/'cmdline').read_bytes().split(b'\0')
            except OSError:continue
            if any(Path(os.fsdecode(a)).name=='script_5_fit_to_post.py' for a in cmd if a):
                parser.error(f'Task-5 writer still running: PID {proc.name}')
    state=root/'CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/STATE/parquet_lake_offload'
    state.mkdir(parents=True,exist_ok=True)
    with (state/'offload.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:parser.error('Another offload is active')
        with (state/'journal.jsonl').open('a') as journal:
            for n in ids:
                station=f'MINGO{n:02d}'
                source=root/f'PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/{station}/STAGE_1_PRODUCTS/EVENT_DATA/PARQUET_LAKE'
                target=dest/station
                if source.is_symlink():
                    if source.resolve()!=target:raise ValueError(f'Unexpected existing lake symlink: {source}')
                    print(f'{station}: already offloaded to {target}',flush=True);continue
                files=entries(source);size=sum(p.stat().st_size for p in files)
                print(f'{station}: {len(files)} parquets; {size/1024**3:.2f} GiB -> {target}',flush=True)
                if not args.apply:continue
                target.mkdir(parents=True,exist_ok=True)
                if shutil.disk_usage(target).free<size+1024**3:
                    raise RuntimeError('Insufficient destination space (requires full source size plus 1 GiB headroom)')
                cache_path=state/f'{station}.json'
                cache=json.loads(cache_path.read_text()) if cache_path.exists() else {}
                verified={}
                for i,p in enumerate(files):
                    verified[p.name]=sync_file(p,target/p.name,cache.get(p.name))
                    cache_path.write_text(json.dumps(verified))
                    if i%100==0:print(f'{station}: verified {i+1}/{len(files)}',flush=True)
                journal.write(json.dumps(dict(event='verified',station=station,files=len(files),bytes=size,dest=str(target)))+'\n');journal.flush()
                if args.activate:
                    activate(source,target,verified,journal)
                    print(f'{station}: activated directory symlink; originals removed after verification',flush=True)
    return 0

if __name__=='__main__':
    try:sys.exit(main())
    except (OSError,ValueError,RuntimeError) as e:print(f'Offload stopped: {e}',file=sys.stderr);sys.exit(2)
