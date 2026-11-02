from pathlib import Path
import re,datetime as dt,json,time
root=Path('/home/mingo/mingo-computing/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS');plan=[]
for station in root.glob('MINGO0[1-4]'):
 lake=station/'STAGE_1_PRODUCTS/EVENT_DATA/PARQUET_LAKE'
 for directory in station.rglob('*'):
  if directory.is_symlink() or not directory.is_dir() or directory.name not in {'ERROR','ERROR_DIRECTORY','COMPLETED','COMPLETED_DIRECTORY'}:continue
  for p in directory.iterdir():
   if p.is_symlink() or not p.is_file() or p.suffix not in {'.parquet','.dat','.hld','.gz'}:continue
   match=re.search(r'mi[0-9]{13}',p.name)
   if not match:continue
   name=match.group();date=dt.datetime.strptime(name[4:9],'%y%j')
   if date>=dt.datetime(2026,10,19) or time.time()-p.stat().st_mtime<86400:continue
   archive=lake/f'postprocessed_{name}.parquet'
   try:
    with archive.open('rb') as f:
     if f.read(4)!=b'PAR1':continue
     f.seek(-4,2)
     if f.read(4)!=b'PAR1':continue
   except OSError:continue
   s=p.stat();plan.append(dict(path=str(p),bytes=s.st_size,mtime_ns=s.st_mtime_ns,archive=str(archive)))
Path(__file__).with_suffix('.json').write_text(json.dumps(plan,indent=2))
size=0;count=0
for r in plan:
 p=Path(r['path'])
 if p.is_symlink() or not p.exists():continue
 s=p.stat()
 if s.st_size!=r['bytes'] or s.st_mtime_ns!=r['mtime_ns']:continue
 p.unlink();size+=s.st_size;count+=1
print('Removed',count,'old lake-backed error/completed files;',round(size/1024**3,3),'GiB. All October-19+ files preserved.')
