import csv,json,fcntl,importlib.util,sys,shutil
from pathlib import Path
import pandas as pd
root=Path('/home/mingo/mingo-computing');base=root/'MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/INTERSTEPS'
p=root/'MINGO_DIGITAL_TWIN/ORCHESTRATOR/maintenance/cascade_cleanup_intersteps.py'
spec=importlib.util.spec_from_file_location('cascade',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
locks=[]
for name in ['sim_enqueue.lock','sim_processing.lock','sim_final.lock']:
 h=(root/'OPERATIONS/OPERATIONS_RUNTIME/LOCKS/cron'/name).open('a');fcntl.flock(h,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(h)
original=m.downstream_manifest_exists;cache={};fail=[]
def validated(step,name,downstream):
 for candidate in downstream.glob(name+'_*'):
  manifest=candidate/f'step_{step+1}_chunks.chunks.json'
  if not manifest.is_file():continue
  if manifest not in cache:
   try:
    d=json.loads(manifest.read_text());n=0
    for item in d['chunks']:
     chunk=candidate/f'step_{step+1}_chunks'/Path(item).name
     if chunk.is_symlink() or not chunk.is_file():raise ValueError('missing/nonregular chunk')
     frame=pd.read_pickle(chunk);n+=len(frame);del frame
    if n!=d['row_count'] or n<=0:raise ValueError('invalid row count')
    cache[manifest]=True
   except Exception as e:cache[manifest]=False;fail.append((str(manifest),str(e)))
  if cache[manifest]:return True
 return False
m.downstream_manifest_exists=validated
plan=[];real_rmtree=shutil.rmtree
m.shutil.rmtree=lambda p,**kw:plan.append(p)
stats=m.run_cleanup(base,base/'STEP_0_TO_1/param_mesh.csv',False)
m.shutil.rmtree=real_rmtree
rows=[]
for p in plan:
 files=[q for q in p.rglob('*') if q.is_file() and not q.is_symlink()]
 rows.append(dict(path=str(p),files=len(files),bytes=sum(q.stat().st_size for q in files)))
out=Path(__file__).parent
(out/'consumed_simulation_plan.json').write_text(json.dumps(dict(stats=stats,targets=rows,invalid_downstream=fail),indent=2))
print('Validated manifests',len(cache),'failed',len(fail),'directories',len(rows),'GiB',sum(r['bytes'] for r in rows)/1024**3,flush=True)
if '--apply' in sys.argv:
 for row in rows:real_rmtree(row['path'])
 print('Deleted validated consumed intermediates only; STEP_10 and pending prefixes retained.',flush=True)
