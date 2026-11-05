import csv, datetime, collections, math
from pathlib import Path
root=Path('/home/mingo/mingo-computing/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO01/STAGE_1')
import bisect
hv=[]
for p in Path('/tmp/mingo_caen_scan_logs').glob('*.log'):
 for line in p.open():
  q=line.split()
  if len(q)>=65:
   try: hv.append((datetime.datetime.fromisoformat(q[0]),tuple(round(float(q[1+ch*8])/1000,4) for ch in range(8))))
   except ValueError: pass
hv.sort(); times=[x[0] for x in hv]

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
out=Path(__file__).resolve().parent
step=root/'EVENT_DATA/STEP_1'
def read(task,kind):
 p=step/f'TASK_{task}/METADATA/task_{task[0]}_metadata_{kind}.csv'
 return {r['filename_base']:r for r in csv.DictReader(p.open())}
t1=read('1_SELFTRIGGER','trigger_type'); t2=read('2_SELFTRIGGER','trigger_type'); sp=read('2_SELFTRIGGER','specific')
groups=collections.defaultdict(lambda:collections.defaultdict(collections.Counter))
matched=0; mismatch=0
for fn in sorted(t1.keys() & t2.keys() & sp.keys()):
 try: start=datetime.datetime.fromisoformat(sp[fn]['data_first_datetime']);end=datetime.datetime.fromisoformat(sp[fn]['data_last_datetime'])
 except (ValueError,KeyError):continue
 i=bisect.bisect_right(times,start)-1;j=bisect.bisect_right(times,end)-1
 if i<0 or start<datetime.datetime(2026,10,19,9,27):continue
 key=hv[i][1]
 if any(v!=key for _,v in hv[i:j+1]):continue
 matched+=1
 for stage,row,prefix in [('Task 1',t1[fn],'tt_task0_raw'),('Task 2',t2[fn],'tt_task2_selftrigger'),('Raw lineage',t2[fn],'tt_task0_raw')]:
  for tt in ('1234','134','124','14'):
   groups[key][stage][tt]+=int(float(row.get(f'{prefix}_{tt}_count') or 0))
 mismatch+=any(t1[fn].get(f'tt_task0_raw_{tt}_count')!=t2[fn].get(f'tt_task0_raw_{tt}_count') for tt in ('1234','134','124','14'))
rows=[]
for key,stages in sorted(groups.items()):
 for stage,counts in stages.items():
  a,b,c,d=[counts[t] for t in ('1234','134','124','14')];n=a+b+c+d
  if not n:continue
  p=np.array([a,b,c,d])/n;q2=p[1]+p[3];q3=p[2]+p[3];pred=q2*q3
  cov=(np.diag(p)-np.outer(p,p))/n;g=np.array([0,q3,q2,q2+q3])
  rows.append(dict(p1_kv=key[0],p2_kv=key[1],stage=stage,N=n,N1234=a,N134=b,N124=c,N14=d,predicted_percent=100*pred,measured_percent=100*p[3],ratio=p[3]/pred if pred else float('nan'),xerr=100*np.sqrt(g@cov@g),yerr=100*np.sqrt(cov[3,3])))
with (out/'stage_comparison.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
fig,axes=plt.subplots(1,2,figsize=(12,6),sharex=True,sharey=True)
limit=max(r['measured_percent']+r['yerr'] for r in rows)*1.15
for ax,stage,color in zip(axes,['Task 1','Task 2'],['tab:blue','tab:orange']):
 for r in rows:
  if r['stage']!=stage:continue
  ax.errorbar(r['predicted_percent'],r['measured_percent'],xerr=r['xerr'],yerr=r['yerr'],fmt='o',color=color,capsize=3)
  ax.annotate(f"{r['p1_kv']:.3f}",(r['predicted_percent'],r['measured_percent']),xytext=(5,5),textcoords='offset points',fontsize=8)
 ax.plot([0,limit],[0,limit],'--',color='.4');ax.set(xlim=(0,limit),ylim=(0,limit),title=stage,xlabel='Predicted joint miss [%]');ax.grid(alpha=.2);ax.set_aspect('equal')
axes[0].set_ylabel('Measured TT14 / (TT1234 + TT134 + TT124 + TT14) [%]')
fig.suptitle('MINGO01 self-trigger · matched source files · labels: P1 HV [kV]')
fig.text(.1,.02,'1σ counting uncertainties; X and Y are correlated. Task 1 preserves raw data; Task 2 recomputes TT after filtering.',fontsize=9)
fig.tight_layout(rect=(0,.06,1,.95))
for ext in ('png','pdf'):fig.savefig(out/f'tt14_stage_comparison.{ext}',dpi=180)
print('Matched files:',matched,'raw-lineage count mismatches:',mismatch)
for r in rows:
 if r['stage']!='Raw lineage':print(f"{r['p1_kv']:.4f} {r['stage']} N={r['N']} pred={r['predicted_percent']:.3f}% measured={r['measured_percent']:.3f}% ratio={r['ratio']:.2f}")
